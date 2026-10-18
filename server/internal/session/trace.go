package session

// 本文件是 rag_trace 的**读取投影**（P1-1 会话详情切片）。
//
// 为什么不能"照着列读"：`chat_messages.rag_trace` 是无 schema 的 JSON 列，历史行里什么形状都有；
// Python 侧之所以能返回稳定形状，是因为 `MessageInfo` 用 pydantic 把它按声明过的字段重新投影了一遍
// （backend/schemas/schemas.py:225 的 wrap 校验器：整条不合法就只留正文）。
// Go 要接管这条接口，就必须产出**同一份投影**，否则浏览器会看到两种形状——那是第二条真相，
// 而第二条真相正是本次接管要消灭的东西（`contracts/p1-design-review.md` §2）。
//
// 字段的权威声明在 `contracts/openapi.yaml` 的 RagTrace 及四个嵌套模型；
// `scripts/check_contracts.py` 三方核对 openapi ↔ Python 模型 ↔ 本文件的字段表，
// 任一处改名/加字段而另两处没跟上，门禁直接红。
//
// 渲染口径逐条对齐 Python：
//   - 未声明的键丢弃；声明了但行里没有的可选键输出 null（响应键集合恒等于声明集合）；
//   - tool_used / tool_name 缺失或不合法 → **整条** rag_trace 为 null，不是逐字段降级；
//   - 嵌套元素不合法同样使整条为 null（pydantic 的 ValidationError 会一路上抛）；
//   - 非 ASCII 原样输出、不转义 <>&，浮点用 Python 的 repr 口径（整数值也带 .0）。

import (
	"bytes"
	"encoding/json"
	"math"
	"regexp"
	"strconv"
	"strings"
)

// 字段种类：本项目只用得上这八种。
const (
	kindString = 's' // str
	kindBool   = 'b' // bool
	kindInt    = 'i' // int
	kindFloat  = 'f' // float
	kindStrInt = 'p' // str | int（页码既可能是 "3" 也可能是 3）
	kindObject = 'o' // 嵌套模型
	kindArray  = 'a' // list[嵌套模型]
	kindMap    = 'm' // dict[str, 嵌套模型]
)

type traceField struct {
	name     string
	kind     byte
	required bool
	elem     *traceSpec
}

type traceSpec struct {
	name   string
	fields []traceField
}

var chunkSpec = &traceSpec{
	name: "RetrievedChunk",
	fields: []traceField{
		{"filename", kindString, true, nil},
		{"page_number", kindStrInt, false, nil},
		{"text", kindString, false, nil},
		{"score", kindFloat, false, nil},
		{"rrf_rank", kindInt, false, nil},
		{"rerank_score", kindFloat, false, nil},
		{"parent_idx", kindInt, false, nil},
		{"child_idx", kindInt, false, nil},
		{"has_theorem_in_parent", kindBool, false, nil},
		{"has_proof_in_parent", kindBool, false, nil},
		{"chapter_path", kindString, false, nil},
	},
}

var sourceRefSpec = &traceSpec{
	name: "SourceReference",
	fields: []traceField{
		{"filename", kindString, false, nil},
		{"page", kindStrInt, false, nil},
		{"chunk_id", kindString, false, nil},
		{"source_label", kindString, false, nil},
	},
}

var citationSpec = &traceSpec{
	name: "CitationInfo",
	fields: []traceField{
		{"claim", kindString, false, nil},
		{"source_label", kindString, false, nil},
		{"filename", kindString, false, nil},
		{"page", kindStrInt, false, nil},
		{"chunk_id", kindString, false, nil},
		{"supported", kindBool, false, nil},
		{"reason", kindString, false, nil},
	},
}

var unsupportedClaimSpec = &traceSpec{
	name: "UnsupportedClaim",
	fields: []traceField{
		{"claim", kindString, true, nil},
		{"reason", kindString, false, nil},
		{"suggested_action", kindString, false, nil},
	},
}

var ragTraceSpec = &traceSpec{
	name: "RagTrace",
	fields: []traceField{
		{"tool_used", kindBool, true, nil},
		{"tool_name", kindString, true, nil},
		{"query", kindString, false, nil},
		{"expanded_query", kindString, false, nil},
		{"step_back_question", kindString, false, nil},
		{"step_back_answer", kindString, false, nil},
		{"expansion_type", kindString, false, nil},
		{"hypothetical_doc", kindString, false, nil},
		{"retrieval_stage", kindString, false, nil},
		{"grade_score", kindString, false, nil},
		{"grade_route", kindString, false, nil},
		{"rewrite_needed", kindBool, false, nil},
		{"rewrite_strategy", kindString, false, nil},
		{"rewrite_query", kindString, false, nil},
		{"rerank_enabled", kindBool, false, nil},
		{"rerank_applied", kindBool, false, nil},
		{"rerank_model", kindString, false, nil},
		{"rerank_endpoint", kindString, false, nil},
		{"rerank_error", kindString, false, nil},
		{"retrieval_mode", kindString, false, nil},
		{"candidate_k", kindInt, false, nil},
		{"leaf_retrieve_level", kindInt, false, nil},
		{"auto_merge_enabled", kindBool, false, nil},
		{"auto_merge_applied", kindBool, false, nil},
		{"auto_merge_threshold", kindInt, false, nil},
		{"auto_merge_replaced_chunks", kindInt, false, nil},
		{"auto_merge_steps", kindInt, false, nil},
		{"context_expansion_enabled", kindBool, false, nil},
		{"context_expansion_applied", kindBool, false, nil},
		{"expand_prev_parent", kindInt, false, nil},
		{"expand_next_parent", kindInt, false, nil},
		{"expand_max_chunks", kindInt, false, nil},
		{"expanded_chunk_count", kindInt, false, nil},
		{"retrieved_chunks", kindArray, false, chunkSpec},
		{"initial_retrieved_chunks", kindArray, false, chunkSpec},
		{"expanded_retrieved_chunks", kindArray, false, chunkSpec},
		{"source_map", kindMap, false, sourceRefSpec},
		{"citations", kindArray, false, citationSpec},
		{"unsupported_claims", kindArray, false, unsupportedClaimSpec},
	},
}

// traceSpecs 是给门禁读的登记表，不是运行时分支。
var traceSpecs = []*traceSpec{ragTraceSpec, chunkSpec, sourceRefSpec, citationSpec, unsupportedClaimSpec}

// projectTrace 把列里的 JSON 原文投影成契约形状。返回 null 的两种来源（列本身为 NULL、
// 历史行不合法）对外不可区分——与 Python 侧一致：追踪是可选诊断信息，不能拖垮已保存正文。
func projectTrace(raw []byte) json.RawMessage {
	if len(raw) == 0 {
		return json.RawMessage("null")
	}
	out, ok := projectObject(raw, ragTraceSpec)
	if !ok {
		return json.RawMessage("null")
	}
	return out
}

type objectEntry struct {
	key   string
	value json.RawMessage
}

// objectEntries 按**文档顺序**读出对象的键值，重复键保留首次出现的位置、取最后一次的值——
// 这正是 Python `json.loads` 的 dict 语义。用 map 会丢顺序，source_map 的键序就会和 Python 漂开。
func objectEntries(raw []byte) ([]objectEntry, bool) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	first, err := dec.Token()
	if err != nil {
		return nil, false
	}
	if delim, ok := first.(json.Delim); !ok || delim != '{' {
		return nil, false
	}
	entries := []objectEntry{}
	index := map[string]int{}
	for dec.More() {
		keyToken, err := dec.Token()
		if err != nil {
			return nil, false
		}
		key, ok := keyToken.(string)
		if !ok {
			return nil, false
		}
		var value json.RawMessage
		if err := dec.Decode(&value); err != nil {
			return nil, false
		}
		if at, seen := index[key]; seen {
			entries[at].value = value
			continue
		}
		index[key] = len(entries)
		entries = append(entries, objectEntry{key: key, value: value})
	}
	if _, err := dec.Token(); err != nil { // 吃掉 '}'：缺了就说明不是完整对象
		return nil, false
	}
	return entries, true
}

func projectObject(raw []byte, spec *traceSpec) (json.RawMessage, bool) {
	entries, ok := objectEntries(raw)
	if !ok {
		return nil, false
	}
	fields := map[string]json.RawMessage{}
	for _, entry := range entries {
		fields[entry.key] = entry.value
	}
	var buf bytes.Buffer
	buf.WriteByte('{')
	for i, field := range spec.fields {
		if i > 0 {
			buf.WriteByte(',')
		}
		key, ok := jsonString(field.name)
		if !ok {
			return nil, false
		}
		buf.Write(key)
		buf.WriteByte(':')
		value, present := fields[field.name]
		if !present {
			// 必需键缺失 → 整条不合法；可选键缺失 → 输出 null，键仍然全量存在。
			if field.required {
				return nil, false
			}
			buf.WriteString("null")
			continue
		}
		out, ok := projectValue(value, field)
		if !ok {
			return nil, false
		}
		buf.Write(out)
	}
	buf.WriteByte('}')
	return json.RawMessage(buf.Bytes()), true
}

func projectArray(raw []byte, spec *traceSpec) (json.RawMessage, bool) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	first, err := dec.Token()
	if err != nil {
		return nil, false
	}
	if delim, ok := first.(json.Delim); !ok || delim != '[' {
		return nil, false
	}
	var buf bytes.Buffer
	buf.WriteByte('[')
	n := 0
	for dec.More() {
		var item json.RawMessage
		if err := dec.Decode(&item); err != nil {
			return nil, false
		}
		if n > 0 {
			buf.WriteByte(',')
		}
		out, ok := projectObject(item, spec)
		if !ok {
			return nil, false
		}
		buf.Write(out)
		n++
	}
	if _, err := dec.Token(); err != nil {
		return nil, false
	}
	buf.WriteByte(']')
	return json.RawMessage(buf.Bytes()), true
}

// projectMap 只服务 source_map：键是任意来源标签字符串，值按声明投影。
func projectMap(raw []byte, spec *traceSpec) (json.RawMessage, bool) {
	entries, ok := objectEntries(raw)
	if !ok {
		return nil, false
	}
	var buf bytes.Buffer
	buf.WriteByte('{')
	for i, entry := range entries {
		if i > 0 {
			buf.WriteByte(',')
		}
		key, ok := jsonString(entry.key)
		if !ok {
			return nil, false
		}
		buf.Write(key)
		buf.WriteByte(':')
		value, ok := projectObject(entry.value, spec)
		if !ok {
			return nil, false
		}
		buf.Write(value)
	}
	buf.WriteByte('}')
	return json.RawMessage(buf.Bytes()), true
}

func projectValue(raw json.RawMessage, field traceField) (json.RawMessage, bool) {
	switch field.kind {
	case kindString:
		var s string
		if json.Unmarshal(raw, &s) != nil {
			return nil, false
		}
		return jsonString(s)
	case kindBool:
		return projectBool(raw)
	case kindInt:
		return projectInt(raw)
	case kindFloat:
		return projectFloat(raw)
	case kindStrInt:
		return projectStrInt(raw)
	case kindObject:
		return projectObject(raw, field.elem)
	case kindArray:
		return projectArray(raw, field.elem)
	case kindMap:
		return projectMap(raw, field.elem)
	}
	return nil, false
}

func projectBool(raw json.RawMessage) (json.RawMessage, bool) {
	if b, ok := scalarBool(raw); ok {
		if b {
			return json.RawMessage("true"), true
		}
		return json.RawMessage("false"), true
	}
	// 历史行里没有写前校验，布尔常被存成字符串或 0/1；这里接受的值集合与 pydantic 的宽松模式一致。
	var s string
	if json.Unmarshal(raw, &s) == nil {
		switch strings.ToLower(s) {
		case "true", "t", "yes", "y", "on", "1":
			return json.RawMessage("true"), true
		case "false", "f", "no", "n", "off", "0":
			return json.RawMessage("false"), true
		}
		return nil, false
	}
	value, ok := numberValue(raw)
	if !ok || (value != 0 && value != 1) || value != math.Trunc(value) {
		return nil, false
	}
	if value == 1 {
		return json.RawMessage("true"), true
	}
	return json.RawMessage("false"), true
}

// scalarBool 只认 JSON 里真正的 true/false 字面量，其它形状一律 ok=false（不猜）。
func scalarBool(raw json.RawMessage) (bool, bool) {
	var b bool
	if json.Unmarshal(raw, &b) != nil {
		return false, false
	}
	return b, true
}

func projectInt(raw json.RawMessage) (json.RawMessage, bool) {
	var i int64
	if json.Unmarshal(raw, &i) == nil {
		return json.RawMessage(strconv.FormatInt(i, 10)), true
	}
	// 布尔落进 int 字段：pydantic 的宽松模式给 1/0，不是报错。
	if b, ok := scalarBool(raw); ok {
		if b {
			return json.RawMessage("1"), true
		}
		return json.RawMessage("0"), true
	}
	// 无损的浮点（3.0）与数字字符串（"10"）在 Python 侧同样能落到 int。
	var f float64
	if json.Unmarshal(raw, &f) == nil {
		if f == math.Trunc(f) && !math.IsInf(f, 0) {
			return json.RawMessage(strconv.FormatInt(int64(f), 10)), true
		}
		return nil, false
	}
	var s string
	if json.Unmarshal(raw, &s) != nil {
		return nil, false
	}
	s = strings.TrimSpace(s)
	if n, err := strconv.ParseInt(s, 10, 64); err == nil {
		return json.RawMessage(strconv.FormatInt(n, 10)), true
	}
	// 定点小数的字符串写法（"10.0"）pydantic 收，指数写法（"1e2"）它拒——
	// 直接丢给 ParseFloat 会让 Go 多接受一种 Python 拒绝的形状。
	if v, err := strconv.ParseFloat(s, 64); err == nil && fixedDecimal.MatchString(s) && v == math.Trunc(v) && !math.IsInf(v, 0) {
		return json.RawMessage(strconv.FormatInt(int64(v), 10)), true
	}
	return nil, false
}

// fixedDecimal 就是 pydantic 字符串转 int 实际接受的形状（可正负的十进制，可带小数部分）。
var fixedDecimal = regexp.MustCompile(`^[+-]?[0-9]+(\.[0-9]+)?$`)

func projectFloat(raw json.RawMessage) (json.RawMessage, bool) {
	var f float64
	if json.Unmarshal(raw, &f) != nil {
		// 布尔落进 float 字段：pydantic 给 1.0/0.0。
		if b, ok := scalarBool(raw); ok {
			f = 0
			if b {
				f = 1
			}
		} else {
			var s string
			if json.Unmarshal(raw, &s) != nil {
				return nil, false
			}
			parsed, err := strconv.ParseFloat(strings.TrimSpace(s), 64)
			if err != nil {
				return nil, false
			}
			f = parsed
		}
	}
	if math.IsNaN(f) || math.IsInf(f, 0) {
		// Python 的 json 渲染对非有限值直接抛错（Starlette 的 allow_nan=False，整条请求 500）；
		// 本项目不会产出它，这里选择降级成 null：正文比一条坏追踪重要，不能让它拖垮整段历史。
		return nil, false
	}
	return json.RawMessage(pythonFloat(f)), true
}

func projectStrInt(raw json.RawMessage) (json.RawMessage, bool) {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return jsonString(s)
	}
	return projectInt(raw)
}

func numberValue(raw json.RawMessage) (float64, bool) {
	var f float64
	if json.Unmarshal(raw, &f) != nil {
		return 0, false
	}
	return f, true
}

// jsonString 复刻 Python 的字符串渲染：非 ASCII 原样输出，且**不**把 < > & 转义成 \u00xx。
// Go 的 encoder 默认转义它们，直接用会让两种语言对同一篇正文给出不同字节。
func jsonString(s string) (json.RawMessage, bool) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(s); err != nil {
		return nil, false
	}
	return json.RawMessage(bytes.TrimRight(buf.Bytes(), "\n")), true
}

// pythonFloat 按 CPython 的 repr 口径渲染：1e16 及以上或 1e-4 以下用指数，其余定点且整数值也带 .0。
// 只用 strconv.FormatFloat(f,'f',-1,64) 会把 3.0 写成 "3"，而 Python 恒写成 "3.0"。
func pythonFloat(f float64) string {
	if f != 0 && (math.Abs(f) >= 1e16 || math.Abs(f) < 1e-4) {
		return strconv.FormatFloat(f, 'e', -1, 64)
	}
	out := strconv.FormatFloat(f, 'f', -1, 64)
	if !strings.Contains(out, ".") {
		out += ".0"
	}
	return out
}
