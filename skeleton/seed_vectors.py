"""
TransitFlow — pgvector Policy Document Seeder
Run once after starting Docker:
    python skeleton/seed_vectors.py
"""

import json
import os
import sys
import time

sys.path.insert(0, ".")

from skeleton.llm_provider import llm
from databases.relational.queries import store_policy_document

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def build_documents():
    
    docs = []

    # 1. 優化 refund_policy.json — 依據時間視窗與補償規則精細拆分
    for policy in _load("refund_policy.json"):
        label = policy.get("label", "退票政策")
        
        # 拆解 cancellation_windows 變成獨立文件
        if "cancellation_windows" in policy:
            for w in policy["cancellation_windows"]:
                title = f"{label} - {w.get('label')}"
                content = (
                    f"項目：{label}。退票條件：{w.get('condition')}。 "
                    f"此狀況下退款比例為 {w.get('refund_percent')}%，行政手續費為 {w.get('admin_fee_usd', 0.0)} USD。"
                )
                if "return_ticket_notes" in policy:
                    content += f" 來回票規範：{policy['return_ticket_notes']}"
                if "no_show_policy" in policy:
                    content += f" 未到（No-show）規範：{policy['no_show_policy']}"
                if "notes" in policy:
                    content += f" 備註：{policy['notes']}"
                    
                docs.append({
                    "title": title,
                    "category": "refund",
                    "source_file": "refund_policy.json",
                    "content": content,
                })
                
        # 拆解 compensation_rules 變成獨立文件
        if "compensation_rules" in policy:
            for r in policy["compensation_rules"]:
                title = f"{label} - 誤點賠償 ({r.get('rule_id')})"
                content = (
                    f"項目：{label}。延誤賠償條件：{r.get('condition')}。 "
                    f"補償方案：{r.get('compensation')}。申請索賠方式：{r.get('how_to_claim')}。"
                )
                if "exclusions" in policy:
                    content += f" 免責/除外條款：{policy['exclusions']}"
                    
                docs.append({
                    "title": title,
                    "category": "refund",
                    "source_file": "refund_policy.json",
                    "content": content,
                })

    # 2. 優化 ticket_types.json — 區分捷運與國鐵的不同發售計費情境
    for tt in _load("ticket_types.json"):
        display_name = tt.get("display_name", "")
        base_desc = tt.get("description", "")
        
        for system in ["metro", "national_rail"]:
            if system in tt:
                system_label = "捷運 (Metro)" if system == "metro" else "國鐵 (National Rail)"
                title = f"票種說明 - {display_name} ({system_label})"
                
                sys_details = tt[system]
                details_str = "；".join([f"{k.replace('_', ' ')}: {v}" for k, v in sys_details.items()])
                content = f"票種名稱：{display_name}。基本描述：{base_desc}。在 {system_label} 的具體規範為：{details_str}"
                
                docs.append({
                    "title": title,
                    "category": "booking",
                    "source_file": "ticket_types.json",
                    "content": content,
                })

    # 3. 優化 booking_rules.json — 拆解成自然語言段落
    br = _load("booking_rules.json")
    for network in ["national_rail", "metro"]:
        if network in br:
            network_label = "國鐵 (National Rail)" if network == "national_rail" else "捷運 (Metro)"
            for topic, details in br[network].items():
                title = f"訂票規則 — {network_label} - {topic.replace('_', ' ').title()}"
                if isinstance(details, dict):
                    details_str = "；".join([f"{k.replace('_', ' ')}: {v}" for k, v in details.items()])
                    content = f"關於 {network_label} 的 {topic} 規定：{details_str}"
                else:
                    content = f"關於 {network_label} 的 {topic} 規定：{details}"
                    
                docs.append({
                    "title": title,
                    "category": "booking",
                    "source_file": "booking_rules.json",
                    "content": content,
                })
                
    if "general_rules" in br:
        for rule_key, rule_text in br["general_rules"].items():
            docs.append({
                "title": f"通用購票規則 — {rule_key.replace('_', ' ').title()}",
                "category": "booking",
                "source_file": "booking_rules.json",
                "content": f"系統通用安全與營運規範【{rule_key}】：{rule_text}",
            })

    # 4. 優化 travel_policies.json — 拆解行李、寵物、腳踏車等獨立情境
    tp = _load("travel_policies.json")
    for network in ["metro", "national_rail"]:
        if network in tp:
            network_label = "捷運 (Metro)" if network == "metro" else "國鐵 (National Rail)"
            for topic, details in tp[network].items():
                title = f"乘車規範 — {network_label} - {topic.replace('_', ' ').title()}"
                
                if isinstance(details, list):
                    content = f"在 {network_label} 上，關於 {topic} 的禁止項目清單：{', '.join(details)}"
                elif isinstance(details, dict):
                    segments = []
                    for sk, sv in details.items():
                        if isinstance(sv, dict):
                            sub_str = " ".join([f"{k}: {v}" for k, v in sv.items()])
                            segments.append(f"[{sk.replace('_', ' ')}] {sub_str}")
                        else:
                            segments.append(f"{sk.replace('_', ' ')}: {sv}")
                    content = f"在 {network_label} 上，關於 {topic} 的乘客須知： " + "；".join(segments)
                else:
                    content = f"在 {network_label} 上，關於 {topic} 的官方規範：{details}"
                    
                docs.append({
                    "title": title,
                    "category": "conduct",  # 配合老師原本設定的 category 名稱
                    "source_file": "travel_policies.json",
                    "content": content,
                })

    return docs


def seed():
    documents = build_documents()
    print(f"📄 Embedding {len(documents)} policy documents using {llm.chat_provider}...\n")

    for i, doc in enumerate(documents):
        print(f"  [{i+1}/{len(documents)}] Embedding: {doc['title']}")

        try:
            # 調用老師寫好的 llm 模組
            embedding = llm.embed(doc["content"])

            if len(embedding) != llm.embed_dim:
                print(f"    ⚠️  Unexpected embedding dim: {len(embedding)} (expected {llm.embed_dim})")
                print(f"    Update GEMINI_EMBED_DIM or OLLAMA_EMBED_DIM in skeleton/config.py")
                sys.exit(1)

            # 這裡調用寫好的資料庫寫入 query
            doc_id = store_policy_document(
                title=doc["title"],
                category=doc["category"],
                content=doc["content"],
                embedding=embedding,
                source_file=doc.get("source_file", ""),
            )
            print(f"    ✓ Stored as document id={doc_id}")

        except Exception as e:
            print(f"    ✗ Failed: {e}")
            raise

        if llm.chat_provider == "gemini" and i < len(documents) - 1:
            time.sleep(0.5)

    print(f"\n✅ All {len(documents)} policy documents embedded and stored.")


if __name__ == "__main__":
    seed()