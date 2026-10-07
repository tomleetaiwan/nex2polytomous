import argparse
import os
import re
from collections import Counter
from math import log2

import pandas as pd

# =====================================================================
# 1. 設定你的 NEX 檔案路徑與輸出的 Markdown 檔案路徑
# =====================================================================
NEXUS_FILE_PATH = "2009-early-and-middle-devonian-phacopidae-of-south-moroccan.nex"  # 👈 請換成你實際的 .nex 檔名
OUTPUT_MD_PATH = "generated/polytomous_key.md"


def _extract_nexus_command(text, command):
    """擷取 NEXUS 指令到未被單引號包住的分號為止。"""
    command_match = re.search(rf"^\s*{re.escape(command)}\b", text, re.IGNORECASE | re.MULTILINE)
    if not command_match:
        return None

    start = command_match.end()
    in_quote = False
    index = start
    while index < len(text):
        char = text[index]
        if char == "'":
            if in_quote and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_quote = not in_quote
        elif char == ";" and not in_quote:
            return text[start:index]
        index += 1

    raise ValueError(f"{command} 區塊缺少結尾分號")


def _split_unquoted(text, separator):
    """依未被 NEXUS 單引號包住的分隔字元切割文字。"""
    parts = []
    start = 0
    in_quote = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if in_quote and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_quote = not in_quote
        elif char == separator and not in_quote:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return parts


def _strip_nexus_comments(text):
    """移除未被單引號包住的 NEXUS 方括號註解，並保留原始換行。"""
    output = []
    comment_depth = 0
    in_quote = False
    index = 0

    while index < len(text):
        char = text[index]
        if comment_depth:
            if char == "[":
                comment_depth += 1
            elif char == "]":
                comment_depth -= 1
            output.append("\n" if char == "\n" else " ")
            index += 1
            continue

        if char == "'":
            output.append(char)
            if in_quote and index + 1 < len(text) and text[index + 1] == "'":
                output.append("'")
                index += 2
                continue
            in_quote = not in_quote
        elif char == "[" and not in_quote:
            comment_depth = 1
            output.append(" ")
        else:
            output.append(char)
        index += 1

    if comment_depth:
        raise ValueError("NEXUS 註解缺少結尾方括號")
    if in_quote:
        raise ValueError("NEXUS 單引號字串缺少結尾引號")
    return "".join(output)


def _tokenize_nexus(text):
    """將 NEXUS 指令內容切成字詞，並處理單引號及兩個單引號的跳脫。"""
    tokens = []
    token = []
    in_quote = False
    index = 0

    while index < len(text):
        char = text[index]
        if in_quote:
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    token.append("'")
                    index += 2
                    continue
                in_quote = False
            else:
                token.append(char)
        elif char == "'":
            in_quote = True
        elif char.isspace() or char == ",":
            if token:
                tokens.append("".join(token))
                token = []
        else:
            token.append(char)
        index += 1

    if in_quote:
        raise ValueError("NEXUS 單引號字串缺少結尾引號")
    if token:
        tokens.append("".join(token))
    return tokens


def parse_statelabels(file_path):
    """解析 STATELABELS，回傳零起算字元索引及各狀態編號對應的說明。"""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    block = _extract_nexus_command(text, "STATELABELS")
    if block is None:
        return {}

    state_labels = {}
    for entry in _split_unquoted(block, ","):
        entry_match = re.match(r"\s*(\d+)\b(.*)", entry, re.DOTALL)
        if not entry_match:
            continue

        character_index = int(entry_match.group(1)) - 1
        labels = [
            quoted.replace("''", "'") if quoted else unquoted
            for quoted, unquoted in re.findall(r"'((?:''|[^'])*)'|([^\s]+)", entry_match.group(2))
        ]
        if labels:
            state_labels[character_index] = dict(enumerate(labels))

    return state_labels


def _format_flag_enabled(format_text, option):
    match = re.search(
        rf"\b{re.escape(option)}\b(?:\s*=\s*(\w+))?",
        format_text,
        re.IGNORECASE,
    )
    return bool(match and (match.group(1) or "YES").upper() not in {"NO", "FALSE", "0"})


def _format_value(format_text, option, default=None):
    match = re.search(
        rf"\b{re.escape(option)}\s*=\s*(?:\"([^\"]*)\"|'((?:''|[^'])*)'|([^\s]+))",
        format_text,
        re.IGNORECASE,
    )
    if not match:
        return default
    value = next(group for group in match.groups() if group is not None)
    return value.replace("''", "'")


def _parse_nexus(file_path):
    """以標準函式庫解析本工具支援的 NEXUS 形態矩陣子集。"""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = _strip_nexus_comments(f.read())

    taxlabels_block = _extract_nexus_command(text, "TAXLABELS")
    if taxlabels_block is None:
        raise ValueError("找不到 TAXLABELS 區塊")
    species_names = _tokenize_nexus(taxlabels_block)
    if not species_names:
        raise ValueError("TAXLABELS 區塊沒有物種名稱")

    ntax_match = re.search(r"\bNTAX\s*=\s*(\d+)", text, re.IGNORECASE)
    if ntax_match and int(ntax_match.group(1)) != len(species_names):
        raise ValueError(
            f"TAXLABELS 有 {len(species_names)} 個物種，但 NTAX={ntax_match.group(1)}"
        )
    nchar_match = re.search(r"NCHAR\s*=\s*(\d+)", text, re.IGNORECASE)
    if not nchar_match:
        raise ValueError("找不到 DIMENSIONS NCHAR")
    num_features = int(nchar_match.group(1))

    format_text = _extract_nexus_command(text, "FORMAT")
    if format_text is None:
        raise ValueError("找不到 FORMAT 區塊")
    datatype = _format_value(format_text, "DATATYPE", "STANDARD")
    if datatype.upper() != "STANDARD":
        raise ValueError(f"不支援 DATATYPE={datatype}；僅支援 STANDARD")
    for unsupported_option in ("INTERLEAVE", "TRANSPOSE", "TOKENS"):
        if _format_flag_enabled(format_text, unsupported_option):
            raise ValueError(f"目前不支援 FORMAT {unsupported_option}")
    for unsupported_option in ("MATCHCHAR", "EQUATE"):
        if _format_value(format_text, unsupported_option) is not None:
            raise ValueError(f"目前不支援 FORMAT {unsupported_option}")

    missing = _format_value(format_text, "MISSING", "?")
    gap = _format_value(format_text, "GAP", "-")
    if len(missing) != 1 or len(gap) != 1:
        raise ValueError("MISSING 與 GAP 必須是單一字元")
    missing_symbols = {missing, gap}

    symbols = _format_value(format_text, "SYMBOLS", "01")
    allowed_states = set(symbols) | missing_symbols
    non_integer_symbols = [symbol for symbol in symbols if not symbol.isdecimal()]
    if non_integer_symbols:
        raise ValueError("本工具僅支援以整數表示的單字元狀態")

    charlabels_block = _extract_nexus_command(text, "CHARLABELS")
    if charlabels_block is None:
        raise ValueError("找不到 CHARLABELS 區塊")
    feature_names = _tokenize_nexus(charlabels_block)
    if len(feature_names) != num_features:
        raise ValueError(
            f"CHARLABELS 有 {len(feature_names)} 個名稱，但 NCHAR={num_features}"
        )

    statelabels_block = _extract_nexus_command(text, "STATELABELS")
    if statelabels_block is None or not statelabels_block.strip():
        raise ValueError("找不到 STATELABELS 區塊或區塊內容為空")

    matrix_block = _extract_nexus_command(text, "MATRIX")
    if matrix_block is None:
        raise ValueError("找不到 MATRIX 區塊")

    raw_rows = {}
    for line_number, line in enumerate(matrix_block.splitlines(), start=1):
        tokens = _tokenize_nexus(line)
        if not tokens:
            continue
        if len(tokens) < 2:
            raise ValueError(f"MATRIX 第 {line_number} 列缺少狀態資料")
        taxon = tokens[0]
        if taxon not in species_names:
            raise ValueError(f"MATRIX 包含未在 TAXLABELS 宣告的物種：{taxon}")
        if taxon in raw_rows:
            raise ValueError(f"MATRIX 物種重複或使用交錯格式：{taxon}")

        states = list("".join(tokens[1:]))
        if len(states) != num_features:
            raise ValueError(
                f"MATRIX 物種 {taxon} 有 {len(states)} 個狀態，但 NCHAR={num_features}"
            )
        invalid_states = sorted(set(states) - allowed_states)
        if invalid_states:
            raise ValueError(
                f"MATRIX 物種 {taxon} 包含 FORMAT SYMBOLS 未宣告的狀態："
                f"{', '.join(invalid_states)}"
            )
        raw_rows[taxon] = states

    missing_taxa = [taxon for taxon in species_names if taxon not in raw_rows]
    if missing_taxa:
        raise ValueError(f"MATRIX 缺少物種資料：{', '.join(missing_taxa)}")
    return species_names, feature_names, raw_rows, missing_symbols


def parse_nexus_to_dataframe(file_path):
    """讀取 NEX 檔案並將形態矩陣轉換為 Pandas DataFrame。

    處理前會先「移除」含有缺失符號 (missing/gap symbol，如 '?' 或 '-') 的特徵欄位，
    確保後續分類樹只根據每個物種都有明確狀態的形態特徵進行分支，
    而不是像過去那樣把缺失值硬轉成 -1 當成一個真實狀態餵給演算法。
    """
    try:
        species_names, feature_names, raw_rows, missing_symbols = _parse_nexus(file_path)
    except (OSError, ValueError) as error:
        print(f"❌ 讀取 NEX 檔案失敗，請檢查格式是否正確。錯誤訊息: {error}")
        return None, None, None

    num_features = len(feature_names)
    state_labels = parse_statelabels(file_path)

    # 先移除任一物種含有缺失符號 (missing/gap) 的特徵欄，而非把缺失值當成 -1 的假資料
    keep_indices = [
        i for i in range(num_features)
        if all(raw_rows[taxon][i] not in missing_symbols for taxon in species_names)
    ]
    removed_count = num_features - len(keep_indices)
    if removed_count:
        print(f"🧹 已移除 {removed_count} 個含有缺失符號 (missing symbols) 的特徵欄位，共保留 {len(keep_indices)} 個。")

    feature_names = [feature_names[i] for i in keep_indices]
    matrix_data = [[int(raw_rows[taxon][i]) for i in keep_indices] for taxon in species_names]
    state_labels = {
        new_index: state_labels[original_index]
        for new_index, original_index in enumerate(keep_indices)
        if original_index in state_labels
    }

    df = pd.DataFrame(matrix_data, columns=feature_names, index=species_names)
    return df, feature_names, state_labels


def build_key_rows(df, feature_names, state_labels, required_features=None):
    """優先使用指定特徵，其餘以 Entropy 建立檢索表資料列。"""
    key_rows = []
    pair_counter = 1
    required_features = required_features or []

    def entropy(row_indices):
        counts = Counter(df.index[row_index] for row_index in row_indices)
        total = len(row_indices)
        return -sum((count / total) * log2(count / total) for count in counts.values())

    def partition_by_state(row_indices, feature_idx):
        partitions = {}
        for row_index in row_indices:
            state = int(df.iloc[row_index, feature_idx])
            partitions.setdefault(state, []).append(row_index)
        return partitions

    def information_gain(row_indices, feature_idx):
        partitions = partition_by_state(row_indices, feature_idx)
        total = len(row_indices)
        remainder = sum(
            len(partition) / total * entropy(partition)
            for partition in partitions.values()
        )
        return entropy(row_indices) - remainder

    def state_text(feature_idx, state):
        labels = state_labels.get(feature_idx, {})
        value = f"{state}（{labels[state]}）" if state in labels else str(state)
        return f"狀態為 {value}"

    def recurse(row_indices, available_features, depth):
        nonlocal pair_counter

        candidate_features = [
            feature_idx for feature_idx in available_features
            if len(partition_by_state(row_indices, feature_idx)) > 1
        ]
        if not candidate_features:
            return

        feature_idx = next(
            (
                required_feature
                for required_feature in required_features
                if required_feature in candidate_features
            ),
            None,
        )
        if feature_idx is None:
            feature_idx = max(
                candidate_features,
                key=lambda candidate: information_gain(row_indices, candidate),
            )
        partitions = partition_by_state(row_indices, feature_idx)

        current_pair = pair_counter
        pair_counter += 1
        remaining_features = [
            candidate for candidate in available_features
            if candidate != feature_idx
        ]

        for branch_index, state in enumerate(sorted(partitions)):
            partition = partitions[state]
            suffix = chr(ord("a") + branch_index)
            step = f"{current_pair}{suffix}"
            feature = feature_names[feature_idx]
            state_value = state_text(feature_idx, state)
            can_split = any(
                len(partition_by_state(partition, candidate)) > 1
                for candidate in remaining_features
            )
            if len(partition) > 1 and can_split:
                key_rows.append((step, feature, state_value, f"前往步驟 {pair_counter}", depth))
                recurse(partition, remaining_features, depth + 1)
            else:
                species = [df.index[row_index] for row_index in partition]
                key_rows.append((step, feature, state_value, species, depth))

    all_rows = list(range(len(df)))
    all_features = list(range(len(feature_names)))
    if len(df) > 1 and any(
        len(partition_by_state(all_rows, feature_idx)) > 1
        for feature_idx in all_features
    ):
        recurse(all_rows, all_features, 0)
    else:
        key_rows.append(("", "", "", list(df.index), 0))

    return key_rows


def prompt_required_features(feature_names, input_fn=None, output_fn=print):
    """列出特徵並取得使用者指定的優先順序，回傳零起算索引。"""
    if input_fn is None:
        input_fn = input

    output_fn("\n可用的形態特徵：")
    for number, feature_name in enumerate(feature_names, start=1):
        output_fn(f"{number}. {feature_name}")

    prompt = (
        "\n請依優先順序輸入必要特徵的序號（以逗點分隔）；"
        "直接按 Enter 則完全採用資訊增益："
    )
    while True:
        raw_value = input_fn(prompt).strip()
        if not raw_value:
            output_fn("未指定必要特徵，將完全採用資訊增益最高者優先。")
            return []

        values = [value.strip() for value in raw_value.replace("，", ",").split(",")]
        try:
            numbers = [int(value) for value in values]
        except ValueError:
            output_fn("輸入格式錯誤：請輸入以逗點分隔的整數序號。")
            continue

        if any(number < 1 or number > len(feature_names) for number in numbers):
            output_fn(f"序號超出範圍：請輸入 1 到 {len(feature_names)} 之間的序號。")
            continue
        if len(numbers) != len(set(numbers)):
            output_fn("必要特徵序號不可重複，請重新輸入。")
            continue

        selected_names = " → ".join(feature_names[number - 1] for number in numbers)
        output_fn(f"必要特徵優先順序：{selected_names}")
        return [number - 1 for number in numbers]


def format_species(species):
    """將各物種名稱分別套用 Markdown 粗斜體。"""
    return " / ".join(f"***{name}***" for name in species)


def _escape_markdown_table_cell(value):
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def _key_row_sort_key(row):
    step = row[0]
    if not step:
        return 0, ""

    match = re.fullmatch(r"(\d+)([A-Za-z]+)", step)
    if not match:
        raise ValueError(f"無法排序的步驟編號：{step!r}")
    return int(match.group(1)), match.group(2).casefold()


def render_key_markdown(key_rows, output_format):
    """將檢索表資料列輸出為縮排文字或 Markdown 表格。"""
    if output_format not in {"indented", "table"}:
        raise ValueError(
            f"不支援的輸出格式：{output_format!r}；請使用 'indented' 或 'table'。"
        )

    sorted_key_rows = sorted(key_rows, key=_key_row_sort_key)

    if output_format == "indented":
        lines = []
        for step, feature, state, result, depth in sorted_key_rows:
            formatted_result = format_species(result) if isinstance(result, list) else result
            if not step:
                lines.append(f"👉 {formatted_result}")
                continue
            indent = "   " * depth
            lines.append(
                f"{indent}{step}. {feature}：{state} -----------------> "
                f"{'👉 ' if isinstance(result, list) else ''}{formatted_result}"
            )
        return "\n".join(lines)

    if output_format == "table":
        lines = [
            "| 編號 | 特徵 | 狀態 | 結果 |",
            "|---|---|---|---|",
        ]
        for step, feature, state, result, _depth in sorted_key_rows:
            formatted_result = format_species(result) if isinstance(result, list) else result
            if isinstance(result, list):
                formatted_result = f"👉 {formatted_result}"
            cells = [
                _escape_markdown_table_cell(value)
                for value in (step, feature, state, formatted_result)
            ]
            lines.append(f"| {' | '.join(cells)} |")
        return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="將 NEXUS 形態矩陣轉換為多分叉檢索表。")
    parser.add_argument(
        "-f",
        "--output-format",
        choices=("table", "indented"),
        default="table",
        help="輸出格式（預設：table）",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(f"正在讀取並解析 NEX 檔案: {NEXUS_FILE_PATH}...")
    df, feature_names, state_labels = parse_nexus_to_dataframe(NEXUS_FILE_PATH)
    if df is None:
        return

    print(f"✅ 成功載入！共偵測到 {len(df)} 個物種，{len(feature_names)} 個形態特徵（已排除含缺失值的特徵）。")
    required_features = prompt_required_features(feature_names)
    key_rows = build_key_rows(
        df,
        feature_names,
        state_labels,
        required_features=required_features,
    )
    key_markdown = render_key_markdown(key_rows, args.output_format)
    title = (
        "Markdown 表格式多分叉檢索表"
        if args.output_format == "table"
        else "傳統編號縮排式多分叉檢索表 (Indented Multi-access Key)"
    )

    output_directory = os.path.dirname(OUTPUT_MD_PATH)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)
    with open(OUTPUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        f.write(f"本檢索表由 NEX 形態矩陣自動優化生成，共包含 {len(df)} 個物種。\n\n---\n\n")
        f.write(key_markdown + "\n")

    print(f"🎉 轉換完成！檢索表已儲存至：{OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
