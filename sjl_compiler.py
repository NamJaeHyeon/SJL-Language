#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from dataclasses import dataclass
from typing import List, Dict, Optional

# 식별자 시작 금지 예약어 목록
FORBIDDEN_PREFIXES = (
    "느", "미친", "ㅗ", "뒤져", "또라이", "미쳤냐", "인실좆", "꺼져", "ㅋ", "새끼"
)

@dataclass
class Statement:
    op: str
    args: List[str]
    raw_text: str

class SJLCompilerError(Exception):
    pass

class SJLCompiler:
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.imported_files = set()

    def is_literal(self, token: str) -> bool:
        """토큰이 'ㅗ'로만 이루어진 정수 리터럴인지 확인"""
        return len(token) > 0 and all(c == 'ㅗ' for c in token)

    def eval_literal(self, token: str) -> int:
        """'ㅗ'의 개수 n에 대해 2^(n-1) 계산"""
        return 1 << (len(token) - 1)

    def is_keyword_start(self, token: str) -> bool:
        """토큰이 다른 명령어 구문의 시작 키워드인지 확인 (변수 선언 초기값 생략 판별용)"""
        if token in ("뒤져", "또라이", "미쳤냐", "인실좆", "꺼져", "ㅋ", "새끼"):
            return True
        if token.startswith("미친") or (token.startswith("느") and token.endswith(";")):
            return True
        return False

    def validate_identifier(self, name: str, context: str = "식별자"):
        """식별자 명명 규칙 검증"""
        if not name:
            raise SJLCompilerError(f"빈 {context}는 사용할 수 없습니다.")
        if ";" in name:
            raise SJLCompilerError(f"{context} '{name}'에 세미콜론(;)을 포함할 수 없습니다.")
        for prefix in FORBIDDEN_PREFIXES:
            if name.startswith(prefix):
                raise SJLCompilerError(
                    f"{context} '{name}'은(는) 금지된 접두사 '{prefix}'(으)로 시작할 수 없습니다."
                )

    def preprocess_and_tokenize(self, file_path: str) -> List[str]:
        """첫 줄만 추출하여 주석을 제거하고, '미친<파일명> 새끼' 임포트를 재귀적으로 인라인 치환"""
        abs_path = os.path.abspath(file_path)
        if abs_path in self.imported_files:
            return []  # 순환 참조 및 중복 임포트 방지
        self.imported_files.add(abs_path)

        if not os.path.exists(abs_path):
            raise SJLCompilerError(f"파일을 찾을 수 없습니다: {abs_path}")

        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 첫 번째 줄바꿈(\n) 이후는 전부 주석 처리하여 무시
        first_line = content.splitlines()[0] if content else ""
        raw_tokens = first_line.split()

        final_tokens = []
        i = 0
        n = len(raw_tokens)
        while i < n:
            tok = raw_tokens[i]
            # '미친<파일명> 새끼' 임포트 구문 처리
            if tok.startswith("미친") and len(tok) > 2 and i + 1 < n and raw_tokens[i + 1] == "새끼":
                import_name = tok[2:]
                import_path = os.path.join(os.path.dirname(abs_path), f"{import_name}.sjl")
                # 임포트 파일이 존재하는 경우 첫 줄 토큰을 인라인 삽입 (없으면 표준 헤더로 간주하고 통과)
                if os.path.exists(import_path):
                    final_tokens.extend(self.preprocess_and_tokenize(import_path))
                i += 2
            else:
                final_tokens.append(tok)
                i += 1

        return final_tokens

    def parse(self, tokens: List[str]) -> List[Statement]:
        """토큰 스트림을 9가지 구문(Statement) 배열로 파싱"""
        stmts: List[Statement] = []
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]

            # 1. 모듈 임포트 (전처리에서 남았거나 가상 모듈인 경우 NOP 처리)
            if tok.startswith("미친") and len(tok) > 2 and i + 1 < n and tokens[i + 1] == "새끼":
                stmts.append(Statement("IMPORT", [tok[2:]], f"{tok} 새끼"))
                i += 2

            # 2. 변수 선언: 느<변수명>; [초기값]
            elif tok.startswith("느") and tok.endswith(";") and len(tok) > 2:
                var_name = tok[1:-1]
                self.validate_identifier(var_name, "변수명")

                # 다음 토큰이 초기값(리터럴 또는 기존 변수)인지 확인
                if i + 1 < n and not self.is_keyword_start(tokens[i + 1]):
                    # 단, 그 다음 토큰이 'ㅋ'이나 '꺼져'라면 다음 토큰은 대입문의 좌변 변수임
                    if i + 2 < n and tokens[i + 2] in ("ㅋ", "꺼져"):
                        stmts.append(Statement("DECL", [var_name, "0"], tok))
                        i += 1
                    else:
                        init_val = tokens[i + 1]
                        stmts.append(Statement("DECL", [var_name, init_val], f"{tok} {init_val}"))
                        i += 2
                else:
                    stmts.append(Statement("DECL", [var_name, "0"], tok))
                    i += 1

            # 6. 표준 출력: 인실좆 <값>
            elif tok == "인실좆":
                if i + 1 >= n:
                    raise SJLCompilerError("'인실좆' 뒤에 출력할 대상이 없습니다.")
                stmts.append(Statement("PRINT", [tokens[i + 1]], f"인실좆 {tokens[i + 1]}"))
                i += 2

            # 7. 라벨 정의: 뒤져 <라벨명>
            elif tok == "뒤져":
                if i + 1 >= n:
                    raise SJLCompilerError("'뒤져' 뒤에 라벨명이 없습니다.")
                label_name = tokens[i + 1]
                self.validate_identifier(label_name, "라벨명")
                stmts.append(Statement("LABEL", [label_name], f"뒤져 {label_name}"))
                i += 2

            # 8. 무조건 점프: 또라이 <라벨명>
            elif tok == "또라이":
                if i + 1 >= n:
                    raise SJLCompilerError("'또라이' 뒤에 이동할 라벨명이 없습니다.")
                label_name = tokens[i + 1]
                self.validate_identifier(label_name, "라벨명")
                stmts.append(Statement("JUMP", [label_name], f"또라이 {label_name}"))
                i += 2

            # 9. 조건부 스킵: 미쳤냐 <변수명>
            elif tok == "미쳤냐":
                if i + 1 >= n:
                    raise SJLCompilerError("'미쳤냐' 뒤에 평가할 변수명이 없습니다.")
                var_name = tokens[i + 1]
                self.validate_identifier(var_name, "변수명")
                stmts.append(Statement("SKIP_IF_NZ", [var_name], f"미쳤냐 {var_name}"))
                i += 2

            # 4. 뺄셈 복합 대입: <변수명> 꺼져 ㅋ <값> (4토큰)
            elif i + 3 < n and tokens[i + 1] == "꺼져" and tokens[i + 2] == "ㅋ":
                self.validate_identifier(tok, "변수명")
                val = tokens[i + 3]
                stmts.append(Statement("SUB_ASSIGN", [tok, val], f"{tok} 꺼져 ㅋ {val}"))
                i += 4

            # 5. 차감 대입: <변수명> ㅋ <값1> 꺼져 <값2> (5토큰)
            elif i + 4 < n and tokens[i + 1] == "ㅋ" and tokens[i + 3] == "꺼져":
                self.validate_identifier(tok, "변수명")
                val1, val2 = tokens[i + 2], tokens[i + 4]
                stmts.append(Statement("ASSIGN_SUB", [tok, val1, val2], f"{tok} ㅋ {val1} 꺼져 {val2}"))
                i += 5

            # 3. 단순 대입: <변수명> ㅋ <값> (3토큰)
            elif i + 2 < n and tokens[i + 1] == "ㅋ":
                self.validate_identifier(tok, "변수명")
                val = tokens[i + 2]
                stmts.append(Statement("ASSIGN", [tok, val], f"{tok} ㅋ {val}"))
                i += 3

            else:
                raise SJLCompilerError(f"구문 분석 오류: 알 수 없는 토큰 패턴 '{tok}' (토큰 인덱스 {i})")

        return stmts

    def format_value_expr(self, token: str) -> str:
        """리터럴('ㅗ...') 또는 변수명을 파이썬 평가식 문자열로 변환"""
        if token == "0":
            return "0"
        if self.is_literal(token):
            return f"{self.eval_literal(token)}"
        self.validate_identifier(token, "값/변수명")
        return f"env[{repr(token)}]"

    def generate_python_code(self, stmts: List[Statement]) -> str:
        """파싱된 Statement 배열을 실행 가능한 파이썬 코드로 컴파일"""
        # 1단계: 라벨 위치(인덱스) 심볼 테이블 구축
        labels: Dict[str, int] = {}
        for idx, stmt in enumerate(stmts):
            if stmt.op == "LABEL":
                lbl = stmt.args[0]
                if lbl in labels:
                    raise SJLCompilerError(f"중복 정의된 라벨입니다: '{lbl}'")
                labels[lbl] = idx

        # 2단계: 점프 대상 라벨 유효성 검증
        for stmt in stmts:
            if stmt.op == "JUMP" and stmt.args[0] not in labels:
                raise SJLCompilerError(f"정의되지 않은 라벨로 이동을 시도했습니다: '{stmt.args[0]}'")

        # 3단계: 파이썬 타겟 코드 생성
        lines = [
            "#!/usr/bin/env python3",
            "# -*- coding: utf-8 -*-",
            "# Generated by SJL-to-Python Compiler",
            "",
            "def main():",
            "    env = {}  # SJL 64-bit integer variable table",
            "    pc = 0    # Program Counter",
            "",
            f"    while pc < {len(stmts)}:",
        ]

        if not stmts:
            lines.append("        break")
        else:
            for idx, stmt in enumerate(stmts):
                cond_keyword = "if" if idx == 0 else "elif"
                lines.append(f"        {cond_keyword} pc == {idx}:  # [{idx}] {stmt.raw_text}")

                if stmt.op in ("IMPORT", "LABEL"):
                    lines.append("            pc += 1")

                elif stmt.op == "DECL":
                    var_name, init_tok = stmt.args
                    val_expr = self.format_value_expr(init_tok)
                    lines.append(f"            env[{repr(var_name)}] = {val_expr}")
                    lines.append("            pc += 1")

                elif stmt.op == "ASSIGN":
                    var_name, val_tok = stmt.args
                    val_expr = self.format_value_expr(val_tok)
                    lines.append(f"            env[{repr(var_name)}] = {val_expr}")
                    lines.append("            pc += 1")

                elif stmt.op == "SUB_ASSIGN":
                    var_name, val_tok = stmt.args
                    val_expr = self.format_value_expr(val_tok)
                    lines.append(f"            env[{repr(var_name)}] -= {val_expr}")
                    lines.append("            pc += 1")

                elif stmt.op == "ASSIGN_SUB":
                    var_name, val1_tok, val2_tok = stmt.args
                    val1_expr = self.format_value_expr(val1_tok)
                    val2_expr = self.format_value_expr(val2_tok)
                    lines.append(f"            env[{repr(var_name)}] = {val1_expr} - {val2_expr}")
                    lines.append("            pc += 1")

                elif stmt.op == "PRINT":
                    val_tok = stmt.args[0]
                    val_expr = self.format_value_expr(val_tok)
                    lines.append(f"            print({val_expr})")
                    lines.append("            pc += 1")

                elif stmt.op == "JUMP":
                    target_pc = labels[stmt.args[0]]
                    lines.append(f"            pc = {target_pc}  # jump to '{stmt.args[0]}'")

                elif stmt.op == "SKIP_IF_NZ":
                    var_name = stmt.args[0]
                    lines.append(f"            if env[{repr(var_name)}] != 0:")
                    lines.append("                pc += 2  # 0이 아니면 다음 명령어 건너뛰기")
                    lines.append("            else:")
                    lines.append("                pc += 1  # 0이면 다음 명령어 실행")

        lines.extend([
            "",
            "if __name__ == '__main__':",
            "    main()",
            ""
        ])
        return "\n".join(lines)

    def compile_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        tokens = self.preprocess_and_tokenize(input_path)
        stmts = self.parse(tokens)
        py_code = self.generate_python_code(stmts)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(py_code)
        return py_code

    def compile_string(self, sjl_code: str) -> str:
        first_line = sjl_code.splitlines()[0] if sjl_code else ""
        tokens = first_line.split()
        stmts = self.parse(tokens)
        return self.generate_python_code(stmts)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python3 sjl_compiler.py <input.sjl> [output.py]")
        sys.exit(1)

    in_file = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) >= 3 else os.path.splitext(in_file)[0] + ".py"

    try:
        compiler = SJLCompiler(os.path.dirname(os.path.abspath(in_file)))
        compiler.compile_file(in_file, out_file)
        print(f"[컴파일 성공] '{in_file}' -> '{out_file}'")
    except SJLCompilerError as e:
        print(f"[컴파일 에러] {e}", file=sys.stderr)
        sys.exit(1)