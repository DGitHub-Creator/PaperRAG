"""chain 层：Go ↔ Python ↔ PostgreSQL 的真实链路契约测试（`09` P0-5，real 级）。

与 integration 层的分界是**有没有第二个进程**：integration 用 TestClient 在同一个
Python 进程里跑完断言，chain 必须让请求真的穿过 go-api、ai-core 与真库。
所以这一层的用例都要求外部先把三个东西起来（`dev.py infra` / `serve` / `go-serve`），
起不来时的行为由 `_runtime.preflight_action` 决定，见那份文件的注释。
"""
