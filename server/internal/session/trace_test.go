package session

import (
	"encoding/json"
	"math"
	"strings"
	"testing"
)

// 投影是本次接管里唯一"看不见的形状"，单测把它钉死：
// 键的全集与顺序、必需键失败就整条 null、宽松转换的取值集合、以及 Python 的渲染口径
// （非 ASCII 不转义、<>& 不转义、浮点带 .0）。跨语言一致性另有 chain 层逐字对拍。

func project(t *testing.T, in string) string {
	t.Helper()
	out := projectTrace([]byte(in))
	var check any
	if err := json.Unmarshal(out, &check); err != nil {
		t.Fatalf("投影结果不是合法 JSON：%s（%v）", out, err)
	}
	return string(out)
}

const fullNullTail = `,"expanded_query":null,"step_back_question":null,"step_back_answer":null,` +
	`"expansion_type":null,"hypothetical_doc":null,"retrieval_stage":null,"grade_score":null,"grade_route":null,` +
	`"rewrite_needed":null,"rewrite_strategy":null,"rewrite_query":null,"rerank_enabled":null,"rerank_applied":null,` +
	`"rerank_model":null,"rerank_endpoint":null,"rerank_error":null,"retrieval_mode":null,"candidate_k":null,` +
	`"leaf_retrieve_level":null,"auto_merge_enabled":null,"auto_merge_applied":null,"auto_merge_threshold":null,` +
	`"auto_merge_replaced_chunks":null,"auto_merge_steps":null,"context_expansion_enabled":null,` +
	`"context_expansion_applied":null,"expand_prev_parent":null,"expand_next_parent":null,"expand_max_chunks":null,` +
	`"expanded_chunk_count":null,"retrieved_chunks":null,"initial_retrieved_chunks":null,` +
	`"expanded_retrieved_chunks":null,"source_map":null,"citations":null,"unsupported_claims":null`

func TestProjectionEmitsEveryDeclaredKeyInOrder(t *testing.T) {
	got := project(t, `{"tool_used":true,"tool_name":"rag","query":"q","who_knows_me":42}`)
	want := `{"tool_used":true,"tool_name":"rag","query":"q"` + fullNullTail + `}`
	if got != want {
		t.Errorf("键序/键集与契约不符：\n got=%s\nwant=%s", got, want)
	}
	// 未声明的键必须被丢弃，而不是原样透传——透传等于承认列里什么都能进响应。
	if strings.Contains(got, "who_knows_me") {
		t.Error("未知键被透传了")
	}
}

func TestProjectionNullsWholeTraceWhenRequiredKeyIsBad(t *testing.T) {
	cases := map[string]string{
		"缺 tool_name":         `{"tool_used":true,"query":"q"}`,
		"缺 tool_used":         `{"tool_name":"rag"}`,
		"tool_used 不是布尔":      `{"tool_used":"maybe","tool_name":"rag"}`,
		"tool_name 不是串":       `{"tool_used":true,"tool_name":7}`,
		"根本不是对象":              `["tool_used"]`,
		"标量":                  `"rag"`,
		"嵌套元素缺必需键":            `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"page_number":3}]}`,
		"unsupported 缺 claim": `{"tool_used":true,"tool_name":"rag","unsupported_claims":[{"reason":"x"}]}`,
	}
	for name, in := range cases {
		if got := project(t, in); got != "null" {
			t.Errorf("%s：期望整条 null，实得 %s", name, got)
		}
	}
}

func TestProjectionMatchesPythonLaxCoercion(t *testing.T) {
	// 历史行没有写前校验，这些形状都真实存在过；每种都要和 pydantic 宽松模式给同一个结果。
	got := project(t, `{"tool_used":"yes","tool_name":"rag","candidate_k":"10",`+
		`"retrieved_chunks":[{"filename":"a.pdf","score":1,"rrf_rank":2.0,"has_proof_in_parent":0}]}`)
	if !strings.Contains(got, `"tool_used":true`) {
		t.Errorf(`"yes" 应转成 true：%s`, got)
	}
	if !strings.Contains(got, `"candidate_k":10`) {
		t.Errorf(`"10" 应转成整数 10：%s`, got)
	}
	// score 声明为 float，整数值也必须渲染成 1.0（Python json.dumps 就这么写）。
	if !strings.Contains(got, `"score":1.0`) {
		t.Errorf(`score 应渲染成 1.0：%s`, got)
	}
	if !strings.Contains(got, `"rrf_rank":2`) {
		t.Errorf(`2.0 应无损转成整数 2：%s`, got)
	}
	if !strings.Contains(got, `"has_proof_in_parent":false`) {
		t.Errorf(`0 应转成 false：%s`, got)
	}
	// 嵌套模型同样补全 11 个声明键。
	if strings.Count(got, `"chapter_path":null`) != 1 {
		t.Errorf("嵌套块应补齐未提供的声明键：%s", got)
	}
}

func TestProjectionCoercionSetMatchesPydanticExactly(t *testing.T) {
	// 本机实测 pydantic 的取值集合，Go 只能一模一样：定点小数字符串收、指数写法拒、
	// 布尔能落进 int 与 float。多接受一种形状 = Go 给出对象而 Python 给 null，浏览器看得见。
	cases := []struct{ name, in, want string }{
		{"int 收 \"10.0\"", `{"tool_used":true,"tool_name":"rag","candidate_k":"10.0"}`, `"candidate_k":10`},
		{"int 收 \" 10 \"", `{"tool_used":true,"tool_name":"rag","candidate_k":" 10 "}`, `"candidate_k":10`},
		{"int 收 \"-3\"", `{"tool_used":true,"tool_name":"rag","candidate_k":"-3"}`, `"candidate_k":-3`},
		{"int 收 true", `{"tool_used":true,"tool_name":"rag","candidate_k":true}`, `"candidate_k":1`},
		{"int 收 false", `{"tool_used":true,"tool_name":"rag","candidate_k":false}`, `"candidate_k":0`},
		{"float 收 true", `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"filename":"a","score":true}]}`, `"score":1.0`},
		{"float 收 \"1e3\"", `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"filename":"a","score":"1e3"}]}`, `"score":1000.0`},
	}
	for _, tc := range cases {
		if got := project(t, tc.in); !strings.Contains(got, tc.want) {
			t.Errorf("%s：期望包含 %s，实得 %s", tc.name, tc.want, got)
		}
	}
	// pydantic 拒绝的形状必须让整条变 null，不是把该字段悄悄丢掉。
	for name, in := range map[string]string{
		`int 拒 "1e2"`:   `{"tool_used":true,"tool_name":"rag","candidate_k":"1e2"}`,
		`int 拒 "10.5"`:  `{"tool_used":true,"tool_name":"rag","candidate_k":"10.5"}`,
		`int 拒 "0x10"`:  `{"tool_used":true,"tool_name":"rag","candidate_k":"0x10"}`,
		`int 拒 10.5`:    `{"tool_used":true,"tool_name":"rag","candidate_k":10.5}`,
		`float 拒 "abc"`: `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"filename":"a","score":"abc"}]}`,
		`bool 拒 "nope"`: `{"tool_used":"nope","tool_name":"rag"}`,
		`bool 拒 2`:      `{"tool_used":2,"tool_name":"rag"}`,
		`str|int 拒 3.5`: `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"filename":"a","page_number":3.5}]}`,
		`str|int 收 3`:   `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"filename":"a","page_number":3}]}`,
		`str|int 收 "7"`: `{"tool_used":true,"tool_name":"rag","retrieved_chunks":[{"filename":"a","page_number":"7"}]}`,
	} {
		got := project(t, in)
		switch name {
		case `str|int 收 3`:
			if !strings.Contains(got, `"page_number":3`) {
				t.Errorf("%s：期望保留整数 3，实得 %s", name, got)
			}
		case `str|int 收 "7"`:
			if !strings.Contains(got, `"page_number":"7"`) {
				t.Errorf("%s：期望原样保留 \"7\"，实得 %s", name, got)
			}
		default:
			if got != "null" {
				t.Errorf("%s：期望整条 null，实得 %s", name, got)
			}
		}
	}
}

func TestProjectionRendersStringsLikeStarlette(t *testing.T) {
	got := project(t, `{"tool_used":true,"tool_name":"rag","query":"中文 <b> & A\u0008"}`)
	if !strings.Contains(got, `"query":"中文 <b> & A\b"`) {
		t.Errorf("应原样输出非 ASCII 与 <>&（Starlette 的 ensure_ascii=False）：%s", got)
	}
	if strings.Contains(got, `\u003c`) || strings.Contains(got, `\u4e2d`) {
		t.Errorf("Go 默认的 HTML/ASCII 转义没关掉：%s", got)
	}
}

func TestProjectionKeepsSourceMapKeyOrderAndLastDuplicate(t *testing.T) {
	got := project(t, `{"tool_used":true,"tool_name":"rag","source_map":`+
		`{"[Source 2]":{"filename":"b.pdf"},"[Source 1]":{"page":3},"[Source 2]":{"filename":"c.pdf"}}}`)
	i2 := strings.Index(got, `"[Source 2]"`)
	i1 := strings.Index(got, `"[Source 1]"`)
	if i2 > i1 {
		t.Errorf("source_map 的键序必须跟文档顺序（Python dict 语义）：%s", got)
	}
	// 重复键：位置取首次出现，值取最后一次——与 json.loads 一致。
	if strings.Count(got, `"[Source 2]"`) != 1 || !strings.Contains(got, `"[Source 2]":{"filename":"c.pdf"`) {
		t.Errorf("重复键应按首次位置+最后一次取值：%s", got)
	}
}

func TestColumnNullStaysNull(t *testing.T) {
	if got := projectTrace(nil); string(got) != "null" {
		t.Errorf(`列本身为 NULL 时必须是 null，实得 %s`, got)
	}
}

func TestPythonFloatNotation(t *testing.T) {
	cases := []struct {
		in   float64
		want string
	}{
		{3.0, "3.0"}, // 整数值的 float 也带 .0
		{0.1, "0.1"}, // 最短往返
		{1e15, "1000000000000000.0"},
		{1e16, "1e+16"}, // CPython 在 1e16 换指数记法
		{1e-5, "1e-05"},
		{0.0001, "0.0001"},
		{math.Copysign(0, -1), "-0.0"}, // Go 常量 -0.0 在编译期就没有符号位，负零得这么造
		{0.0, "0.0"},
		{2.5e-7, "2.5e-07"},
	}
	for _, tc := range cases {
		if got := pythonFloat(tc.in); got != tc.want {
			t.Errorf("pythonFloat(%v) = %s，期望 %s", tc.in, got, tc.want)
		}
	}
}
