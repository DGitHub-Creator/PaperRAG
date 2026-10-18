package observability

// 追踪号接受集合的 Go 侧单测（契约 components.parameters.TraceId，台账 C38）。
//
// 这里钉的是**取值集合**：哪些入站值被沿用、哪些被换成新生成的 16 位十六进制。
// Python 侧有一份同形态的用例（tests/unit/test_trace_header.py），三方字面量是否同一条
// 规则由 scripts/check_contracts.py 核对——漂移的代价是日志关联悄悄断掉，不是报错。

import (
	"regexp"
	"strings"
	"testing"
)

var generated16 = regexp.MustCompile(`^[0-9a-f]{16}$`)

func TestLegalTraceIDsAreCarriedThrough(t *testing.T) {
	for _, in := range []string{
		"a", "0", "abc-DEF_1.2", strings.Repeat("a", 128),
		"deadbeefdeadbeef", "00000000000000000000000000000001", // Python 的 32 位形态也必须能沿用
	} {
		if got := SanitizeTraceID(in); got != in {
			t.Errorf("%q 合法却被换成 %q", in, got)
		}
	}
}

func TestIllegalTraceIDsAreReplacedNotEchoed(t *testing.T) {
	cases := map[string]string{
		"缺失":         "",
		"超长":         strings.Repeat("a", 129),
		"含空格":        "abc def",
		"含换行":        "abc\n",
		"非 ASCII":    "追踪",
		"含冒号":        "a:b",
		"含斜杠":        "a/b",
		"带方括号的复合值":   "['abcdef', 'fedcba']",
		"逗号并起来的重复头值": "abcdef,fedcba",
		"含引号":        `"abc"`,
	}
	for label, in := range cases {
		got := SanitizeTraceID(in)
		if got == in {
			t.Errorf("%s：非法值被原样沿用了", label)
		}
		if !generated16.MatchString(got) {
			t.Errorf("%s：生成值不符合契约形状 %q", label, got)
		}
	}
}

func TestGeneratedTraceIDsDoNotRepeat(t *testing.T) {
	seen := make(map[string]bool, 50)
	for range 50 {
		id := SanitizeTraceID("")
		if seen[id] {
			t.Fatalf("追踪号重复了：%s", id)
		}
		seen[id] = true
	}
}
