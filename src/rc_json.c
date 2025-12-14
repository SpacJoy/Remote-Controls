/*
 * rc_json.c
 *
 * 轻量 JSON 解析/序列化实现（UTF-8）。
 *
 * 数据结构：
 * - object：单向链表 RC_JsonPair(key,value)
 * - array ：单向链表 RC_JsonArrayItem(value)
 *
 * 取舍：
 * - 以简单、可移植为优先（不依赖外部 JSON 库）。
 * - 适用于本项目配置文件读写与 GUI 配置生成。
 */

#include "rc_json.h"

#include <ctype.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct RC_JsonPair
{
    char *key;
    struct RC_Json *value;
    struct RC_JsonPair *next;
} RC_JsonPair;

typedef struct RC_JsonArrayItem
{
    struct RC_Json *value;
    struct RC_JsonArrayItem *next;
} RC_JsonArrayItem;

struct RC_Json
{
    RC_JsonType type;
    union
    {
        double number;
        bool boolean;
        char *string;
        struct
        {
            RC_JsonPair *head;
        } object;
        struct
        {
            RC_JsonArrayItem *head;
        } array;
    } u;
};

typedef struct Parser
{
    const char *s;
    size_t i;
    RC_JsonError *err;
} Parser;

static void set_err(Parser *p, const char *msg)
{
    if (!p || !p->err)
        return;
    p->err->offset = p->i;
    p->err->message = msg;
}

static void skip_ws(Parser *p)
{
    while (p && p->s[p->i] && (p->s[p->i] == ' ' || p->s[p->i] == '\t' || p->s[p->i] == '\r' || p->s[p->i] == '\n'))
        p->i++;
}

static RC_Json *alloc_node(RC_JsonType t)
{
    RC_Json *n = (RC_Json *)calloc(1, sizeof(RC_Json));
    if (!n)
        return NULL;
    n->type = t;
    return n;
}

static bool hexval(char c, int *out)
{
    if (c >= '0' && c <= '9')
    {
        *out = c - '0';
        return true;
    }
    if (c >= 'a' && c <= 'f')
    {
        *out = 10 + (c - 'a');
        return true;
    }
    if (c >= 'A' && c <= 'F')
    {
        *out = 10 + (c - 'A');
        return true;
    }
    return false;
}

static bool utf8_append(char **buf, size_t *len, size_t *cap, const char *bytes, size_t n)
{
    if (*len + n + 1 > *cap)
    {
        size_t newcap = (*cap == 0) ? 64 : *cap;
        while (newcap < *len + n + 1)
            newcap *= 2;
        char *nb = (char *)realloc(*buf, newcap);
        if (!nb)
            return false;
        *buf = nb;
        *cap = newcap;
    }
    memcpy(*buf + *len, bytes, n);
    *len += n;
    (*buf)[*len] = '\0';
    return true;
}

static bool utf8_append_codepoint(char **buf, size_t *len, size_t *cap, unsigned cp)
{
    unsigned char out[4];
    size_t n = 0;

    if (cp <= 0x7F)
    {
        out[0] = (unsigned char)cp;
        n = 1;
    }
    else if (cp <= 0x7FF)
    {
        out[0] = (unsigned char)(0xC0 | ((cp >> 6) & 0x1F));
        out[1] = (unsigned char)(0x80 | (cp & 0x3F));
        n = 2;
    }
    else if (cp <= 0xFFFF)
    {
        out[0] = (unsigned char)(0xE0 | ((cp >> 12) & 0x0F));
        out[1] = (unsigned char)(0x80 | ((cp >> 6) & 0x3F));
        out[2] = (unsigned char)(0x80 | (cp & 0x3F));
        n = 3;
    }
    else if (cp <= 0x10FFFF)
    {
        out[0] = (unsigned char)(0xF0 | ((cp >> 18) & 0x07));
        out[1] = (unsigned char)(0x80 | ((cp >> 12) & 0x3F));
        out[2] = (unsigned char)(0x80 | ((cp >> 6) & 0x3F));
        out[3] = (unsigned char)(0x80 | (cp & 0x3F));
        n = 4;
    }
    else
    {
        return false;
    }

    return utf8_append(buf, len, cap, (const char *)out, n);
}

static unsigned decode_surrogate(unsigned hi, unsigned lo)
{
    // hi: D800-DBFF, lo: DC00-DFFF
    return 0x10000 + (((hi - 0xD800) << 10) | (lo - 0xDC00));
}

static char *parse_string(Parser *p)
{
    if (!p || p->s[p->i] != '"')
        return NULL;
    p->i++; // skip '"'

    char *buf = NULL;
    size_t len = 0, cap = 0;

    while (p->s[p->i])
    {
        char c = p->s[p->i];
        if (c == '"')
        {
            p->i++;
            return buf ? buf : (char *)calloc(1, 1);
        }
        if ((unsigned char)c < 0x20)
        {
            set_err(p, "control character in string");
            free(buf);
            return NULL;
        }
        if (c == '\\')
        {
            p->i++;
            char e = p->s[p->i];
            if (!e)
            {
                set_err(p, "unterminated escape");
                free(buf);
                return NULL;
            }
            p->i++;
            switch (e)
            {
            case '"':
            case '\\':
            case '/':
                if (!utf8_append(&buf, &len, &cap, &e, 1))
                    goto oom;
                break;
            case 'b':
            {
                char b = '\b';
                if (!utf8_append(&buf, &len, &cap, &b, 1))
                    goto oom;
                break;
            }
            case 'f':
            {
                char f = '\f';
                if (!utf8_append(&buf, &len, &cap, &f, 1))
                    goto oom;
                break;
            }
            case 'n':
            {
                char n = '\n';
                if (!utf8_append(&buf, &len, &cap, &n, 1))
                    goto oom;
                break;
            }
            case 'r':
            {
                char r = '\r';
                if (!utf8_append(&buf, &len, &cap, &r, 1))
                    goto oom;
                break;
            }
            case 't':
            {
                char t = '\t';
                if (!utf8_append(&buf, &len, &cap, &t, 1))
                    goto oom;
                break;
            }
            case 'u':
            {
                // \uXXXX
                int h1, h2, h3, h4;
                if (!hexval(p->s[p->i + 0], &h1) || !hexval(p->s[p->i + 1], &h2) ||
                    !hexval(p->s[p->i + 2], &h3) || !hexval(p->s[p->i + 3], &h4))
                {
                    set_err(p, "invalid unicode escape");
                    free(buf);
                    return NULL;
                }
                unsigned u = (unsigned)((h1 << 12) | (h2 << 8) | (h3 << 4) | h4);
                p->i += 4;

                // surrogate pair?
                if (u >= 0xD800 && u <= 0xDBFF)
                {
                    if (p->s[p->i] == '\\' && p->s[p->i + 1] == 'u')
                    {
                        size_t save = p->i;
                        p->i += 2;
                        int l1, l2, l3, l4;
                        if (hexval(p->s[p->i + 0], &l1) && hexval(p->s[p->i + 1], &l2) &&
                            hexval(p->s[p->i + 2], &l3) && hexval(p->s[p->i + 3], &l4))
                        {
                            unsigned lo = (unsigned)((l1 << 12) | (l2 << 8) | (l3 << 4) | l4);
                            if (lo >= 0xDC00 && lo <= 0xDFFF)
                            {
                                p->i += 4;
                                unsigned cp = decode_surrogate(u, lo);
                                if (!utf8_append_codepoint(&buf, &len, &cap, cp))
                                    goto oom;
                                break;
                            }
                        }
                        // invalid pair; backtrack
                        p->i = save;
                    }
                    set_err(p, "invalid surrogate pair");
                    free(buf);
                    return NULL;
                }
                if (u >= 0xDC00 && u <= 0xDFFF)
                {
                    set_err(p, "unexpected low surrogate");
                    free(buf);
                    return NULL;
                }
                if (!utf8_append_codepoint(&buf, &len, &cap, u))
                    goto oom;
                break;
            }
            default:
                set_err(p, "invalid escape");
                free(buf);
                return NULL;
            }
            continue;
        }

        if (!utf8_append(&buf, &len, &cap, &c, 1))
            goto oom;
        p->i++;
    }

    set_err(p, "unterminated string");
    free(buf);
    return NULL;

oom:
    set_err(p, "out of memory");
    free(buf);
    return NULL;
}

static bool match_lit(Parser *p, const char *lit)
{
    size_t n = strlen(lit);
    if (strncmp(p->s + p->i, lit, n) == 0)
    {
        p->i += n;
        return true;
    }
    return false;
}

static RC_Json *parse_value(Parser *p);

static RC_Json *parse_array(Parser *p)
{
    if (p->s[p->i] != '[')
        return NULL;
    p->i++;
    skip_ws(p);

    RC_Json *arr = alloc_node(RC_JSON_ARRAY);
    if (!arr)
    {
        set_err(p, "out of memory");
        return NULL;
    }

    RC_JsonArrayItem **tail = &arr->u.array.head;

    if (p->s[p->i] == ']')
    {
        p->i++;
        return arr;
    }

    while (1)
    {
        skip_ws(p);
        RC_Json *val = parse_value(p);
        if (!val)
        {
            RC_JsonFree(arr);
            return NULL;
        }
        RC_JsonArrayItem *it = (RC_JsonArrayItem *)calloc(1, sizeof(RC_JsonArrayItem));
        if (!it)
        {
            RC_JsonFree(val);
            RC_JsonFree(arr);
            set_err(p, "out of memory");
            return NULL;
        }
        it->value = val;
        *tail = it;
        tail = &it->next;

        skip_ws(p);
        if (p->s[p->i] == ',')
        {
            p->i++;
            continue;
        }
        if (p->s[p->i] == ']')
        {
            p->i++;
            return arr;
        }
        set_err(p, "expected ',' or ']'");
        RC_JsonFree(arr);
        return NULL;
    }
}

static RC_Json *parse_object(Parser *p)
{
    if (p->s[p->i] != '{')
        return NULL;
    p->i++;
    skip_ws(p);

    RC_Json *obj = alloc_node(RC_JSON_OBJECT);
    if (!obj)
    {
        set_err(p, "out of memory");
        return NULL;
    }

    RC_JsonPair **tail = &obj->u.object.head;

    if (p->s[p->i] == '}')
    {
        p->i++;
        return obj;
    }

    while (1)
    {
        skip_ws(p);
        if (p->s[p->i] != '"')
        {
            set_err(p, "expected string key");
            RC_JsonFree(obj);
            return NULL;
        }
        char *key = parse_string(p);
        if (!key)
        {
            RC_JsonFree(obj);
            return NULL;
        }
        skip_ws(p);
        if (p->s[p->i] != ':')
        {
            free(key);
            set_err(p, "expected ':'");
            RC_JsonFree(obj);
            return NULL;
        }
        p->i++;
        skip_ws(p);
        RC_Json *val = parse_value(p);
        if (!val)
        {
            free(key);
            RC_JsonFree(obj);
            return NULL;
        }
        RC_JsonPair *pair = (RC_JsonPair *)calloc(1, sizeof(RC_JsonPair));
        if (!pair)
        {
            free(key);
            RC_JsonFree(val);
            RC_JsonFree(obj);
            set_err(p, "out of memory");
            return NULL;
        }
        pair->key = key;
        pair->value = val;
        *tail = pair;
        tail = &pair->next;

        skip_ws(p);
        if (p->s[p->i] == ',')
        {
            p->i++;
            continue;
        }
        if (p->s[p->i] == '}')
        {
            p->i++;
            return obj;
        }
        set_err(p, "expected ',' or '}'");
        RC_JsonFree(obj);
        return NULL;
    }
}

static RC_Json *parse_number(Parser *p)
{
    size_t start = p->i;
    const char *s = p->s;

    if (s[p->i] == '-')
        p->i++;

    if (!isdigit((unsigned char)s[p->i]))
    {
        set_err(p, "invalid number");
        return NULL;
    }

    if (s[p->i] == '0')
    {
        p->i++;
    }
    else
    {
        while (isdigit((unsigned char)s[p->i]))
            p->i++;
    }

    if (s[p->i] == '.')
    {
        p->i++;
        if (!isdigit((unsigned char)s[p->i]))
        {
            set_err(p, "invalid number fraction");
            return NULL;
        }
        while (isdigit((unsigned char)s[p->i]))
            p->i++;
    }

    if (s[p->i] == 'e' || s[p->i] == 'E')
    {
        p->i++;
        if (s[p->i] == '+' || s[p->i] == '-')
            p->i++;
        if (!isdigit((unsigned char)s[p->i]))
        {
            set_err(p, "invalid number exponent");
            return NULL;
        }
        while (isdigit((unsigned char)s[p->i]))
            p->i++;
    }

    size_t n = p->i - start;
    char tmp[64];
    if (n >= sizeof(tmp))
    {
        set_err(p, "number too long");
        return NULL;
    }
    memcpy(tmp, s + start, n);
    tmp[n] = '\0';

    char *endp = NULL;
    double v = strtod(tmp, &endp);
    if (!endp || *endp != '\0')
    {
        set_err(p, "invalid number");
        return NULL;
    }

    RC_Json *num = alloc_node(RC_JSON_NUMBER);
    if (!num)
    {
        set_err(p, "out of memory");
        return NULL;
    }
    num->u.number = v;
    return num;
}

static RC_Json *parse_value(Parser *p)
{
    skip_ws(p);
    char c = p->s[p->i];
    if (!c)
    {
        set_err(p, "unexpected end of input");
        return NULL;
    }

    if (c == '"')
    {
        char *str = parse_string(p);
        if (!str)
            return NULL;
        RC_Json *n = alloc_node(RC_JSON_STRING);
        if (!n)
        {
            free(str);
            set_err(p, "out of memory");
            return NULL;
        }
        n->u.string = str;
        return n;
    }
    if (c == '{')
        return parse_object(p);
    if (c == '[')
        return parse_array(p);
    if (c == '-' || isdigit((unsigned char)c))
        return parse_number(p);
    if (match_lit(p, "true"))
    {
        RC_Json *n = alloc_node(RC_JSON_BOOL);
        if (!n)
        {
            set_err(p, "out of memory");
            return NULL;
        }
        n->u.boolean = true;
        return n;
    }
    if (match_lit(p, "false"))
    {
        RC_Json *n = alloc_node(RC_JSON_BOOL);
        if (!n)
        {
            set_err(p, "out of memory");
            return NULL;
        }
        n->u.boolean = false;
        return n;
    }
    if (match_lit(p, "null"))
    {
        RC_Json *n = alloc_node(RC_JSON_NULL);
        if (!n)
        {
            set_err(p, "out of memory");
            return NULL;
        }
        return n;
    }

    set_err(p, "invalid value");
    return NULL;
}

RC_Json *RC_JsonParse(const char *text, RC_JsonError *err)
{
    if (err)
    {
        err->offset = 0;
        err->message = NULL;
    }
    if (!text)
        text = "";

    Parser p = {0};
    p.s = text;
    p.i = 0;
    p.err = err;

    skip_ws(&p);
    RC_Json *root = parse_value(&p);
    if (!root)
        return NULL;
    skip_ws(&p);
    if (p.s[p.i] != '\0')
    {
        set_err(&p, "trailing characters");
        RC_JsonFree(root);
        return NULL;
    }
    return root;
}

static void free_pairs(RC_JsonPair *pair)
{
    while (pair)
    {
        RC_JsonPair *next = pair->next;
        free(pair->key);
        RC_JsonFree(pair->value);
        free(pair);
        pair = next;
    }
}

static void free_array(RC_JsonArrayItem *it)
{
    while (it)
    {
        RC_JsonArrayItem *next = it->next;
        RC_JsonFree(it->value);
        free(it);
        it = next;
    }
}

void RC_JsonFree(RC_Json *node)
{
    if (!node)
        return;
    switch (node->type)
    {
    case RC_JSON_STRING:
        free(node->u.string);
        break;
    case RC_JSON_OBJECT:
        free_pairs(node->u.object.head);
        break;
    case RC_JSON_ARRAY:
        free_array(node->u.array.head);
        break;
    default:
        break;
    }
    free(node);
}

RC_JsonType RC_JsonGetType(const RC_Json *node)
{
    return node ? node->type : RC_JSON_NULL;
}

bool RC_JsonIsObject(const RC_Json *node) { return node && node->type == RC_JSON_OBJECT; }
bool RC_JsonIsArray(const RC_Json *node) { return node && node->type == RC_JSON_ARRAY; }
bool RC_JsonIsString(const RC_Json *node) { return node && node->type == RC_JSON_STRING; }
bool RC_JsonIsNumber(const RC_Json *node) { return node && node->type == RC_JSON_NUMBER; }
bool RC_JsonIsBool(const RC_Json *node) { return node && node->type == RC_JSON_BOOL; }

const char *RC_JsonGetString(const RC_Json *node)
{
    if (!node || node->type != RC_JSON_STRING)
        return NULL;
    return node->u.string;
}

int RC_JsonGetInt(const RC_Json *node, int defVal)
{
    if (!node)
        return defVal;
    if (node->type == RC_JSON_NUMBER)
    {
        double v = node->u.number;
        if (v < (double)INT_MIN || v > (double)INT_MAX)
            return defVal;
        return (int)llround(v);
    }
    if (node->type == RC_JSON_BOOL)
        return node->u.boolean ? 1 : 0;
    return defVal;
}

bool RC_JsonGetBool(const RC_Json *node, bool defVal)
{
    if (!node)
        return defVal;
    if (node->type == RC_JSON_BOOL)
        return node->u.boolean;
    if (node->type == RC_JSON_NUMBER)
        return node->u.number != 0.0;
    return defVal;
}

RC_Json *RC_JsonObjectGet(const RC_Json *obj, const char *key)
{
    if (!obj || obj->type != RC_JSON_OBJECT || !key)
        return NULL;
    for (RC_JsonPair *p = obj->u.object.head; p; p = p->next)
    {
        if (p->key && strcmp(p->key, key) == 0)
            return p->value;
    }
    return NULL;
}

static RC_JsonPair *object_find_pair(RC_Json *obj, const char *key)
{
    if (!obj || obj->type != RC_JSON_OBJECT || !key)
        return NULL;
    for (RC_JsonPair *p = obj->u.object.head; p; p = p->next)
    {
        if (p->key && strcmp(p->key, key) == 0)
            return p;
    }
    return NULL;
}

static bool object_set_value(RC_Json *obj, const char *key, RC_Json *val)
{
    if (!obj || obj->type != RC_JSON_OBJECT || !key || !val)
        return false;

    RC_JsonPair *existing = object_find_pair(obj, key);
    if (existing)
    {
        RC_JsonFree(existing->value);
        existing->value = val;
        return true;
    }

    RC_JsonPair *pair = (RC_JsonPair *)calloc(1, sizeof(RC_JsonPair));
    if (!pair)
        return false;
    pair->key = _strdup(key);
    if (!pair->key)
    {
        free(pair);
        return false;
    }
    pair->value = val;

    // append
    if (!obj->u.object.head)
    {
        obj->u.object.head = pair;
        return true;
    }
    RC_JsonPair *tail = obj->u.object.head;
    while (tail->next)
        tail = tail->next;
    tail->next = pair;
    return true;
}

bool RC_JsonObjectSetString(RC_Json *obj, const char *key, const char *val)
{
    RC_Json *n = alloc_node(RC_JSON_STRING);
    if (!n)
        return false;
    n->u.string = _strdup(val ? val : "");
    if (!n->u.string)
    {
        RC_JsonFree(n);
        return false;
    }
    return object_set_value(obj, key, n);
}

bool RC_JsonObjectSetNumber(RC_Json *obj, const char *key, double val)
{
    RC_Json *n = alloc_node(RC_JSON_NUMBER);
    if (!n)
        return false;
    n->u.number = val;
    return object_set_value(obj, key, n);
}

bool RC_JsonObjectSetBool(RC_Json *obj, const char *key, bool val)
{
    RC_Json *n = alloc_node(RC_JSON_BOOL);
    if (!n)
        return false;
    n->u.boolean = val;
    return object_set_value(obj, key, n);
}

typedef struct StrBuf
{
    char *buf;
    size_t len;
    size_t cap;
} StrBuf;

static bool sb_append(StrBuf *sb, const char *s)
{
    size_t n = s ? strlen(s) : 0;
    if (sb->len + n + 1 > sb->cap)
    {
        size_t newcap = (sb->cap == 0) ? 256 : sb->cap;
        while (newcap < sb->len + n + 1)
            newcap *= 2;
        char *nb = (char *)realloc(sb->buf, newcap);
        if (!nb)
            return false;
        sb->buf = nb;
        sb->cap = newcap;
    }
    if (n)
        memcpy(sb->buf + sb->len, s, n);
    sb->len += n;
    sb->buf[sb->len] = '\0';
    return true;
}

static bool sb_append_char(StrBuf *sb, char c)
{
    char tmp[2] = {c, 0};
    return sb_append(sb, tmp);
}

static bool sb_indent(StrBuf *sb, int indent)
{
    for (int i = 0; i < indent; i++)
    {
        if (!sb_append(sb, "  "))
            return false;
    }
    return true;
}

static bool sb_escape_json_string(StrBuf *sb, const char *s)
{
    if (!sb_append_char(sb, '"'))
        return false;
    for (const unsigned char *p = (const unsigned char *)(s ? s : ""); *p; p++)
    {
        unsigned char c = *p;
        switch (c)
        {
        case '"':
            if (!sb_append(sb, "\\\""))
                return false;
            break;
        case '\\':
            if (!sb_append(sb, "\\\\"))
                return false;
            break;
        case '\b':
            if (!sb_append(sb, "\\b"))
                return false;
            break;
        case '\f':
            if (!sb_append(sb, "\\f"))
                return false;
            break;
        case '\n':
            if (!sb_append(sb, "\\n"))
                return false;
            break;
        case '\r':
            if (!sb_append(sb, "\\r"))
                return false;
            break;
        case '\t':
            if (!sb_append(sb, "\\t"))
                return false;
            break;
        default:
            if (c < 0x20)
            {
                char tmp[8];
                sprintf_s(tmp, sizeof(tmp), "\\u%04X", (unsigned)c);
                if (!sb_append(sb, tmp))
                    return false;
            }
            else
            {
                if (!sb_append_char(sb, (char)c))
                    return false;
            }
            break;
        }
    }
    return sb_append_char(sb, '"');
}

static bool print_node(StrBuf *sb, const RC_Json *n, int indent);

static bool print_object(StrBuf *sb, const RC_Json *n, int indent)
{
    if (!sb_append(sb, "{\n"))
        return false;

    RC_JsonPair *p = n->u.object.head;
    while (p)
    {
        if (!sb_indent(sb, indent + 1))
            return false;
        if (!sb_escape_json_string(sb, p->key ? p->key : ""))
            return false;
        if (!sb_append(sb, ": "))
            return false;
        if (!print_node(sb, p->value, indent + 1))
            return false;
        if (p->next)
        {
            if (!sb_append(sb, ",\n"))
                return false;
        }
        else
        {
            if (!sb_append(sb, "\n"))
                return false;
        }
        p = p->next;
    }

    if (!sb_indent(sb, indent))
        return false;
    return sb_append(sb, "}");
}

static bool print_array(StrBuf *sb, const RC_Json *n, int indent)
{
    if (!sb_append(sb, "[\n"))
        return false;

    RC_JsonArrayItem *it = n->u.array.head;
    while (it)
    {
        if (!sb_indent(sb, indent + 1))
            return false;
        if (!print_node(sb, it->value, indent + 1))
            return false;
        if (it->next)
        {
            if (!sb_append(sb, ",\n"))
                return false;
        }
        else
        {
            if (!sb_append(sb, "\n"))
                return false;
        }
        it = it->next;
    }

    if (!sb_indent(sb, indent))
        return false;
    return sb_append(sb, "]");
}

static bool print_node(StrBuf *sb, const RC_Json *n, int indent)
{
    if (!n)
        return sb_append(sb, "null");

    switch (n->type)
    {
    case RC_JSON_NULL:
        return sb_append(sb, "null");
    case RC_JSON_BOOL:
        return sb_append(sb, n->u.boolean ? "true" : "false");
    case RC_JSON_NUMBER:
    {
        char tmp[64];
        // Print like cJSON-ish: avoid trailing .0 when possible
        double v = n->u.number;
        if (fabs(v - (double)llround(v)) < 1e-12 && v >= (double)LLONG_MIN && v <= (double)LLONG_MAX)
            sprintf_s(tmp, sizeof(tmp), "%lld", (long long)llround(v));
        else
            sprintf_s(tmp, sizeof(tmp), "%.15g", v);
        return sb_append(sb, tmp);
    }
    case RC_JSON_STRING:
        return sb_escape_json_string(sb, n->u.string);
    case RC_JSON_OBJECT:
        return print_object(sb, n, indent);
    case RC_JSON_ARRAY:
        return print_array(sb, n, indent);
    default:
        return false;
    }
}

char *RC_JsonPrintPretty(const RC_Json *node)
{
    StrBuf sb = {0};
    if (!print_node(&sb, node, 0))
    {
        free(sb.buf);
        return NULL;
    }
    if (!sb_append(&sb, "\n"))
    {
        free(sb.buf);
        return NULL;
    }
    return sb.buf;
}
