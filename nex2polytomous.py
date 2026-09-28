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


def _parse_with_biopython(file_path):
    """優先使用 Biopython 解析標準 NEXUS 檔案，回傳原始（未去除缺失值）的字元矩陣"""
    from Bio.Nexus import Nexus  # 正確用法：從 Bio.Nexus 匯入 Nexus 類別

    nex = Nexus.Nexus(file_path)
    species_names = list(nex.taxlabels)
    first_taxon = species_names[0]
    num_features = len(nex.matrix[first_taxon])

    if getattr(nex, "charlabels", None):
        feature_names = [nex.charlabels.get(i, f"Char_{i + 1}") for i in range(num_features)]
    else:
        feature_names = [f"Char_{i + 1}" for i in range(num_features)]

    raw_rows = {taxon: [str(state) for state in nex.matrix[taxon]] for taxon in species_names}
    missing_symbols = {str(nex.missing), str(nex.gap)}
    return species_names, feature_names, raw_rows, missing_symbols


def _parse_with_regex_fallback(file_path):
    """當 Biopython 無法解析（例如某些 MorphoBank 匯出格式的 CHARLABELS 語法）時，
    改用簡易正規表示式直接讀取 TAXLABELS / FORMAT / MATRIX 區塊。"""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    taxlabels_match = re.search(r"TAXLABELS(.*?);", text, re.IGNORECASE | re.DOTALL)
    if not taxlabels_match:
        raise ValueError("找不到 TAXLABELS 區塊")
    species_names = [a or b for a, b in re.findall(r"'([^']*)'|(\S+)", taxlabels_match.group(1))]

    missing_match = re.search(r"MISSING\s*=\s*(\S)", text, re.IGNORECASE)
    gap_match = re.search(r"GAP\s*=\s*(\S)", text, re.IGNORECASE)
    missing_symbols = {missing_match.group(1) if missing_match else "?",
                        gap_match.group(1) if gap_match else "-"}

    nchar_match = re.search(r"NCHAR\s*=\s*(\d+)", text, re.IGNORECASE)
    num_features = int(nchar_match.group(1)) if nchar_match else None

    matrix_match = re.search(r"MATRIX(.*?);", text, re.IGNORECASE | re.DOTALL)
    if not matrix_match:
        raise ValueError("找不到 MATRIX 區塊")

    raw_rows = {}
    for line in matrix_match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        row_match = re.match(r"'([^']*)'\s+(\S+)$", line) or re.match(r"(\S+)\s+(\S+)$", line)
        if row_match and row_match.group(1) in species_names:
            raw_rows[row_match.group(1)] = list(row_match.group(2))

    if num_features is None and raw_rows:
        num_features = len(next(iter(raw_rows.values())))
    feature_names = [f"Char_{i + 1}" for i in range(num_features or 0)]

    # 盡量從 CHARLABELS 內類似 [1] 'label' 的格式取得特徵名稱（若解析失敗則維持 Char_N）
    for idx_str, label in re.findall(r"\[(\d+)\]\s*'([^']*)'", text):
        idx = int(idx_str) - 1
        if 0 <= idx < len(feature_names):
            feature_names[idx] = label

    species_names = [s for s in species_names if s in raw_rows]
    return species_names, feature_names, raw_rows, missing_symbols


def parse_nexus_to_dataframe(file_path):
    """讀取 NEX 檔案並將形態矩陣轉換為 Pandas DataFrame。

    處理前會先「移除」含有缺失符號 (missing/gap symbol，如 '?' 或 '-') 的特徵欄位，
    確保後續分類樹只根據每個物種都有明確狀態的形態特徵進行分支，
    而不是像過去那樣把缺失值硬轉成 -1 當成一個真實狀態餵給演算法。
    """
    try:
        species_names, feature_names, raw_rows, missing_symbols = _parse_with_biopython(file_path)
    except Exception as e:
        print(f"⚠️ Biopython 解析失敗（{e}），改用簡易格式解析器重試...")
        try:
            species_names, feature_names, raw_rows, missing_symbols = _parse_with_regex_fallback(file_path)
        except Exception as e2:
            print(f"❌ 讀取 NEX 檔案失敗，請檢查格式是否正確。錯誤訊息: {e2}")
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

# 2. 執行解析
print(f"正在讀取並解析 NEX 檔案: {NEXUS_FILE_PATH}...")
df, feature_names, state_labels = parse_nexus_to_dataframe(NEXUS_FILE_PATH)

if df is not None:
    print(f"✅ 成功載入！共偵測到 {len(df)} 個物種，{len(feature_names)} 個形態特徵（已排除含缺失值的特徵）。")

    # 3. 以 Entropy 計算最佳多分支特徵
    key_lines = []
    pair_counter = 1

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

    def state_description(feature_idx, state):
        labels = state_labels.get(feature_idx, {})
        state_text = f"{state}（{labels[state]}）" if state in labels else str(state)
        return f"{feature_names[feature_idx]}：狀態為 {state_text}"

    def recurse(row_indices, available_features, depth):
        global pair_counter
        indent = "   " * depth  # 控制視覺縮排

        candidate_features = [
            feature_idx for feature_idx in available_features
            if len(partition_by_state(row_indices, feature_idx)) > 1
        ]
        if not candidate_features:
            return

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
            desc = state_description(feature_idx, state)
            can_split = any(
                len(partition_by_state(partition, candidate)) > 1
                for candidate in remaining_features
            )
            if len(partition) > 1 and can_split:
                key_lines.append(f"{indent}{current_pair}{suffix}. {desc} -----------------> 前往步驟 {pair_counter}")
                recurse(partition, remaining_features, depth + 1)
            else:
                species = " / ".join(df.index[row_index] for row_index in partition)
                key_lines.append(f"{indent}{current_pair}{suffix}. {desc} -----------------> 👉 **{species}**")

    # 開始建立檢索表結構
    all_rows = list(range(len(df)))
    all_features = list(range(len(feature_names)))
    if len(df) > 1 and any(
        len(partition_by_state(all_rows, feature_idx)) > 1
        for feature_idx in all_features
    ):
        recurse(all_rows, all_features, 0)
    else:
        key_lines.append(f"👉 **{' / '.join(df.index)}**")

    # 4. 輸出成 Markdown 檔案
    os.makedirs(os.path.dirname(OUTPUT_MD_PATH), exist_ok=True)
    with open(OUTPUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("# 傳統編號縮排式多分叉檢索表 (Indented Multi-access Key)\n")
        f.write(f"本檢索表由 NEX 形態矩陣自動優化生成，共包含 {len(df)} 個物種。\n\n---\n\n")
        for line in key_lines:
            f.write(line + "\n")
            
    print(f"🎉 轉換完成！檢索表已儲存至：{OUTPUT_MD_PATH}")
