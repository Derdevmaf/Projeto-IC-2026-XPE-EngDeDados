"""
extract_tools.py
================
Extrai a tabela de ferramentas do PDF "2025 State of Data and AI Engineering by lakeFS"
e exporta dois arquivos:
  - tools.csv           : domain | goal | tool | url  (apenas tools)
  - tools_hierarchy.csv : level | domain | goal | tool | url  (hierarquia completa destacada)

Estrategia:
  1. Abre o PDF com PyMuPDF e extrai todos os 342 hyperlinks (1 por ferramenta).
  2. Extrai spans de texto para identificar DOMAIN (branco) e GOAL (azul-escuro).
  3. Determina o DOMAIN de cada link por faixas X fixas (calculadas dos midpoints entre domains)
     com split vertical (Y) para a coluna compartilhada DATA VERSION CONTROL / METADATA.
  4. Determina o GOAL pelo span mais proximo acima dentro da mesma faixa X.
  5. Gera tools.csv e tools_hierarchy.csv com a hierarquia DOMAIN > GOAL > TOOL.
"""

import pymupdf as fitz
import pandas as pd
from urllib.parse import urlparse

PDF_PATH      = "2025 State of Data and AI Engineering by lakeFS.pdf"
CSV_TOOLS     = "tools_temp.csv"
CSV_HIERARCHY = "tools_hierarchy_temp.csv"

# Cores do PDF
COLOR_DOMAIN = 0xffffff   # branco  -> DOMAIN
COLOR_GOAL   = 0x171f33   # azul-escuro -> GOAL
SIZE_HEADER  = 14.5

IGNORE_AS_DOMAIN = {"State of Data and AI Engineering 2025"}
IGNORE_AS_TOOL   = {"state of data and ai engineering 2025", "explore the table", "nan", ""}

# ---------------------------------------------------------------------------
# Ordem canonica (layout visual do infografico, esquerda para direita)
# ---------------------------------------------------------------------------
DOMAIN_ORDER = [
    "INGEST",
    "DATA LAKE",
    "DATA VERSION CONTROL",
    "METADATA",
    "COMPUTE ENGINES",
    "PIPELINES",
    "PRACTITIONER APPS",
    "GOVERNANCE",
]

GOAL_ORDER = {
    "INGEST":               ["Ingest Tech", "Ingest SaaS", "Reverse ETL"],
    "DATA LAKE":            ["Object Storage"],
    "DATA VERSION CONTROL": ["Data Version Control"],
    "METADATA":             ["Metastores", "Open Table Formats"],
    "COMPUTE ENGINES":      ["Distributed Compute", "Analytics Engines"],
    "PIPELINES":            ["Orchestration", "Data Quality / Observability"],
    "PRACTITIONER APPS":    ["MLOps End-to-End", "Data Centric AI/ML",
                             "ML/AI Observability & Monitoring", "Vector DBs",
                             "Notebooks", "Analytics Workflows"],
    "GOVERNANCE":           ["Data Catalog / Governance"],
}

# ---------------------------------------------------------------------------
# Limites de coluna X (midpoints entre domains adjacentes, calculados a mao
# a partir das coordenadas inspecionadas):
#   INGEST cx~133, DATA LAKE cx~314, DVC cx~475, COMPUTE cx~675,
#   PIPELINES cx~898, PRACTITIONER cx~1342, GOVERNANCE cx~1785
#
# Coluna compartilhada DVC / METADATA (x: 394-575):
#   y < 461 -> DATA VERSION CONTROL
#   y >= 461 -> METADATA   (cabecalho METADATA em y=461)
# ---------------------------------------------------------------------------
COLUMN_RULES = [
    # (x_min, x_max, domain_or_func)
    (0,    223,  "INGEST"),
    (223,  394,  "DATA LAKE"),
    (394,  575,  None),          # split por Y -> ver abaixo
    (575,  787,  "COMPUTE ENGINES"),
    (787,  1120, "PIPELINES"),
    (1120, 1563, "PRACTITIONER APPS"),
    (1563, 9999, "GOVERNANCE"),
]
# Y de divisao na coluna compartilhada (y0 do span METADATA = 461)
Y_METADATA_SPLIT = 461.0


def find_domain_for_point(cx, cy):
    """Retorna o DOMAIN a que pertence o ponto (cx, cy)."""
    for x_min, x_max, domain in COLUMN_RULES:
        if x_min <= cx < x_max:
            if domain is not None:
                return domain
            # Coluna compartilhada DATA VERSION CONTROL / METADATA
            return "DATA VERSION CONTROL" if cy < Y_METADATA_SPLIT else "METADATA"
    return "GOVERNANCE"  # fallback


# ---------------------------------------------------------------------------
# Mapeamento URI -> nome da ferramenta
# ---------------------------------------------------------------------------
URL_TO_NAME = {
    "hadoop.apache.org/docs/r1.2.1/hdfs_design":    "Apache HDFS",
    "hadoop.apache.org/docs/r1.2.1/mapred_tutorial": "MapReduce",
    "hadoop.apache.org":                             "Apache Hadoop",
    "aws.amazon.com/s3":                             "Amazon S3",
    "zadara.com":                                    "Zadara",
    "cloudflare.com/developer-platform/r2":          "Cloudflare R2",
    "min.io":                                        "MinIO",
    "alibabacloud.com/product/oss":                  "Alibaba Cloud OSS",
    "oracle.com/cloud/storage":                      "Oracle Cloud Storage",
    "azure.microsoft.com/products/storage/blobs":    "Azure Blob Storage",
    "ibm.com/cloud":                                 "IBM Cloud Object Storage",
    "digitalocean.com/products/spaces":              "DigitalOcean Spaces",
    "aws.amazon.com/kinesis":                        "Amazon Kinesis",
    "storm.apache.org":                              "Apache Storm",
    "snowplow.io":                                   "Snowplow",
    "airbyte.com":                                   "Airbyte",
    "pulsar.apache.org":                             "Apache Pulsar",
    "wasabi.com":                                    "Wasabi",
    "ceph.io":                                       "Ceph",
    "purestorage.com":                               "Pure Storage",
    "netapp.com":                                    "NetApp StorageGRID",
    "storj.io":                                      "Storj",
    "vastdata.com":                                  "VAST Data",
    "aws.amazon.com/redshift":                       "Amazon Redshift",
    "snowflake.com":                                 "Snowflake",
    "aws.amazon.com/athena":                         "Amazon Athena",
    "dremio.com":                                    "Dremio",
    "druid.apache.org":                              "Apache Druid",
    "startree.ai":                                   "StarTree",
    "qubole.com":                                    "Qubole",
    "pentaho.com":                                   "Pentaho",
    "imply.io":                                      "Imply",
    "ascend.io":                                     "Ascend.io",
    "cloud.google.com/dataflow":                     "Google Dataflow",
    "trino.io":                                      "Trino",
    "aws.amazon.com/emr":                            "Amazon EMR",
    "akka.io":                                       "Akka",
    "github.com/dask/dask":                          "Dask",
    "azure.microsoft.com/en-us/services/hdinsight":  "Azure HDInsight",
    "firebolt.io":                                   "Firebolt",
    "starrocks.io":                                  "StarRocks",
    "kylin.apache.org":                              "Apache Kylin",
    "cloud.google.com/bigquery":                     "Google BigQuery",
    "github.com/apache/arrow-datafusion":            "Apache Arrow DataFusion",
    "starburst.io":                                  "Starburst",
    "yellowbrick.com":                               "Yellowbrick",
    "clickhouse.tech":                               "ClickHouse",
    "clickhouse.com":                                "ClickHouse",
    "hazelcast.com":                                 "Hazelcast",
    "shipyardapp.com":                               "Shipyard",
    "elementary-data.com":                           "Elementary",
    "informatica.com":                               "Informatica",
    "talend.com":                                    "Talend",
    "matillion.com":                                 "Matillion",
    "meltano.com":                                   "Meltano",
    "fivetran.com":                                  "Fivetran",
    "hevodata.com":                                  "Hevo Data",
    "stitchdata.com":                                "Stitch",
    "debezium.io":                                   "Debezium",
    "kafka.apache.org":                              "Apache Kafka",
    "confluent.io":                                  "Confluent",
    "nifi.apache.org":                               "Apache NiFi",
    "flink.apache.org":                              "Apache Flink",
    "spark.apache.org":                              "Apache Spark",
    "getdbt.com":                                    "dbt",
    "dataform.co":                                   "Dataform",
    "dagster.io":                                    "Dagster",
    "airflow.apache.org":                            "Apache Airflow",
    "prefect.io":                                    "Prefect",
    "luigi.readthedocs.io":                          "Luigi",
    "iceberg.apache.org":                            "Apache Iceberg",
    "delta.io":                                      "Delta Lake",
    "hudi.apache.org":                               "Apache Hudi",
    "lakefs.io":                                     "lakeFS",
    "dvc.org":                                       "DVC",
    "pachyderm.com":                                 "Pachyderm",
    "greatexpectations.io":                          "Great Expectations",
    "soda.io":                                       "Soda",
    "montecarlodata.com":                            "Monte Carlo",
    "acceldata.io":                                  "Acceldata",
    "atlan.com":                                     "Atlan",
    "alation.com":                                   "Alation",
    "collibra.com":                                  "Collibra",
    "datahubproject.io":                             "DataHub",
    "open-metadata.org":                             "OpenMetadata",
    "mlflow.org":                                    "MLflow",
    "kubeflow.org":                                  "Kubeflow",
    "aws.amazon.com/sagemaker":                      "Amazon SageMaker",
    "cloud.google.com/vertex-ai":                    "Google Vertex AI",
    "feast.dev":                                     "Feast",
    "tecton.ai":                                     "Tecton",
    "ray.io":                                        "Ray",
    "dask.org":                                      "Dask",
    "grafana.com":                                   "Grafana",
    "prometheus.io":                                 "Prometheus",
    "datadoghq.com":                                 "Datadog",
    "opentelemetry.io":                              "OpenTelemetry",
    "lightdash.com":                                 "Lightdash",
    "metabase.com":                                  "Metabase",
    "superset.apache.org":                           "Apache Superset",
    "looker.com":                                    "Looker",
    "tableau.com":                                   "Tableau",
    "powerbi.microsoft.com":                         "Power BI",
    "mode.com":                                      "Mode",
    "hex.tech":                                      "Hex",
    "evidence.dev":                                  "Evidence",
    "tensorflow.org":                                "TensorFlow",
    "pytorch.org":                                   "PyTorch",
    "huggingface.co":                                "Hugging Face",
    "langchain.com":                                 "LangChain",
    "openai.com":                                    "OpenAI",
    "anthropic.com":                                 "Anthropic",
    "cohere.com":                                    "Cohere",
    "weaviate.io":                                   "Weaviate",
    "pinecone.io":                                   "Pinecone",
    "qdrant.tech":                                   "Qdrant",
    "trychroma.com":                                 "Chroma",
    "milvus.io":                                     "Milvus",
    "cloud.google.com/pubsub":                       "Google Cloud Pub/Sub",
    "cloud.google.com/storage":                      "Google Cloud Storage",
    "cloud.google.com/dataproc":                     "Google Cloud Dataproc",
    "azure.microsoft.com/en-us/products/purview":    "Microsoft Purview",
    "databricks.com/product/unity-catalog":          "Unity Catalog",
    "databricks.com/product/delta-live-tables":      "Delta Live Tables",
    "databricks.com/product/collaborative-notebooks":"Databricks Notebooks",
    "databricks.com/product/data-lakehouse":         "Databricks Lakehouse",
    "databricks.com":                                "Databricks",
    "duckdb.org":                                    "DuckDB",
    "impala.apache.org":                             "Apache Impala",
    "hive.apache.org":                               "Apache Hive",
    "zeppelin.apache.org":                           "Apache Zeppelin",
    "jupyter.org":                                   "Jupyter",
    "dstack.ai":                                     "dstack",
    "aws.amazon.com/lake-formation":                 "AWS Lake Formation",
    "aws.amazon.com/glue":                           "AWS Glue",
    "airtable.com":                                  None,   # link decorativo
    "pinot.apache.org":                              "Apache Pinot",
    "hydra.so":                                      "Hydra",
    "materialize.com":                               "Materialize",
    "questdb.io":                                    "QuestDB",
    "pola.rs":                                       "Polars",
    "lakesoul-io.github.io":                         "LakeSoul",
    "kx.com":                                        "Kx",
    "linkedin.com/company/rocksetcloud":             "Rockset",
    "rockset.com":                                   "Rockset",
    "singlestore.com":                               "SingleStore",
    "voltrondata.com":                               "Voltron Data",
    "redis.io":                                      "Redis",
    "doris.apache.org":                              "Apache Doris",
    "beam.apache.org":                               "Apache Beam",
    "kaskada.com":                                   "Kaskada",
    "memphis.dev":                                   "Memphis",
    "redpanda.com":                                  "Redpanda",
    "streamnative.io":                               "StreamNative",
    "striim.com":                                    "Striim",
    "upsolver.com":                                  "Upsolver",
    "warpstream.com":                                "WarpStream",
    "dataddo.com":                                   "Dataddo",
    "estuary.dev":                                   "Estuary",
    "integrate.io":                                  "Integrate.io",
    "keboola.com":                                   "Keboola",
    "polytomic.com":                                 "Polytomic",
    "portable.io":                                   "Portable",
    "rivery.io":                                     "Rivery",
    "rudderstack.com":                               "RudderStack",
    "segment.com":                                   "Segment",
    "census.dev":                                    "Census",
    "grouparoo.com":                                 "Grouparoo",
    "hightouch.com":                                 "Hightouch",
    "omnata.com":                                    "Omnata",
    "syncari.com":                                   "Syncari",
}


def uri_to_name(uri):
    uri_clean = uri.rstrip("/ \r\n")
    parsed    = urlparse(uri_clean)
    netloc    = parsed.netloc.replace("www.", "")
    full_path = netloc + parsed.path.rstrip("/")
    for key, name in URL_TO_NAME.items():
        if key in full_path:
            return name
    parts = netloc.split(".")
    return parts[-2].capitalize() if len(parts) >= 2 else netloc


def extract_all_spans(page):
    spans = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for b in blocks:
        if b["type"] != 0: continue
        for line in b["lines"]:
            for span in line["spans"]:
                t = span["text"].strip()
                if not t: continue
                spans.append({
                    "text":  t,
                    "color": span["color"],
                    "size":  span["size"],
                    "x0":    span["bbox"][0],
                    "y0":    span["bbox"][1],
                    "x1":    span["bbox"][2],
                    "y1":    span["bbox"][3],
                    "cx":    (span["bbox"][0] + span["bbox"][2]) / 2,
                    "cy":    (span["bbox"][1] + span["bbox"][3]) / 2,
                })
    return spans


def get_text_in_rect(page, rect, expand=5):
    r     = fitz.Rect(rect.x0 - expand, rect.y0 - expand, rect.x1 + expand, rect.y1 + expand)
    words = page.get_text("words", clip=r)
    if not words: return ""
    return " ".join(w[4] for w in sorted(words, key=lambda w: (round(w[1] / 5), w[0]))).strip()


def merge_multiline(items):
    merged, used = [], set()
    for i, item in enumerate(items):
        if i in used: continue
        mi = dict(item)
        for j in range(i + 1, min(i + 4, len(items))):
            nxt = items[j]
            if j in used: continue
            if abs(nxt["x0"] - item["x0"]) < 80 and abs(nxt["y0"] - mi["y1"]) < 30:
                mi["text"] += " " + nxt["text"]
                mi["y1"] = nxt["y1"]
                used.add(j)
        merged.append(mi)
    return merged


def classify_spans(spans):
    domains, goals = [], []
    valid_domains = {d.lower() for d in DOMAIN_ORDER}
    valid_goals = {g.lower() for glist in GOAL_ORDER.values() for g in glist}
    for s in spans:
        if s["text"] in IGNORE_AS_DOMAIN: continue
        is_domain = (s["color"] == COLOR_DOMAIN and s["size"] >= SIZE_HEADER) or s["text"].lower() in valid_domains
        is_goal = (s["color"] == COLOR_GOAL and s["size"] >= SIZE_HEADER) or s["text"].lower() in valid_goals
        if is_domain:
            domains.append(s)
        elif is_goal:
            goals.append(s)
    return domains, goals


def find_goal_for_point(cx, cy, goals):
    """
    Encontra o GOAL mais proximo ACIMA do ponto dentro da mesma faixa X de coluna.
    A faixa X de coluna do ponto e calculada por find_domain_for_point (COLUMN_RULES).
    """
    # Determina a faixa x da coluna
    col_x0, col_x1 = 0, 9999
    for x_min, x_max, _ in COLUMN_RULES:
        if x_min <= cx < x_max:
            col_x0, col_x1 = x_min, x_max
            break

    candidates = []
    for g in goals:
        # O goal deve estar na mesma coluna ou interceptar
        g_in_col = not (g["x1"] < col_x0 - 40 or g["x0"] > col_x1 + 40)
        above    = g["cy"] <= cy + 10
        if g_in_col and above:
            candidates.append((cy - g["cy"], g["text"]))

    if candidates:
        candidates.sort()
        return candidates[0][1]

    # Fallback: goal mais proximo sem restricao de coluna
    fallback = [(abs(cx - g["cx"]) + abs(cy - g["cy"]) * 0.3, g["text"])
                for g in goals if g["cy"] <= cy + 10]
    if fallback:
        fallback.sort()
        return fallback[0][1]
    return ""


# ---------------------------------------------------------------------------
# CSV hierarquico
# ---------------------------------------------------------------------------
def build_hierarchy_csv(df_tools):
    def d_key(d):
        try: return DOMAIN_ORDER.index(d)
        except ValueError: return len(DOMAIN_ORDER)

    def g_key(d, g):
        order = GOAL_ORDER.get(d, [])
        try: return order.index(g)
        except ValueError: return len(order)

    df = df_tools.copy()
    df["_d"] = df["domain"].apply(d_key)
    df["_g"] = df.apply(lambda r: g_key(r["domain"], r["goal"]), axis=1)
    df.sort_values(["_d", "_g", "tool"], inplace=True)
    df.drop(columns=["_d", "_g"], inplace=True)

    rows, domains_seen, goals_seen = [], set(), set()
    for _, row in df.iterrows():
        d, g, t, u = (str(row[c]).strip() for c in ["domain", "goal", "tool", "url"])
        if t.lower() in IGNORE_AS_TOOL: continue
        if d not in domains_seen:
            rows.append({"level": "DOMAIN", "domain": d, "goal": "", "tool": "", "url": ""})
            domains_seen.add(d)
        if (d, g) not in goals_seen:
            rows.append({"level": "GOAL", "domain": d, "goal": g, "tool": "", "url": ""})
            goals_seen.add((d, g))
        rows.append({"level": "TOOL", "domain": d, "goal": g, "tool": t, "url": u})

    return pd.DataFrame(rows, columns=["level", "domain", "goal", "tool", "url"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("[1/6] Abrindo PDF:", PDF_PATH)
    doc  = fitz.open(PDF_PATH)
    page = doc[0]

    print("[2/6] Extraindo hiperlinks do PDF...")
    links = [
        {"rect": fitz.Rect(lk["from"]), "uri": lk.get("uri", "").strip()}
        for lk in page.get_links()
        if lk.get("kind") == fitz.LINK_URI and lk.get("uri", "").strip()
    ]
    print(f"      {len(links)} link(s) encontrado(s).")

    print("[3/6] Extraindo spans (DOMAIN / GOAL)...")
    spans          = extract_all_spans(page)
    domains_raw, goals_raw = classify_spans(spans)
    domains        = merge_multiline(domains_raw)
    goals          = merge_multiline(goals_raw)
    print(f"      {len(domains)} domain(s): {[d['text'] for d in domains]}")
    print(f"      {len(goals)} goal(s):   {[g['text'] for g in goals]}")

    print("[4/6] Montando hierarquia domain -> goal -> tool...")
    rows = []
    for lk in links:
        rect = lk["rect"]
        uri  = lk["uri"]
        cx   = (rect.x0 + rect.x1) / 2
        cy   = (rect.y0 + rect.y1) / 2

        tool_name = get_text_in_rect(page, rect)
        if not tool_name or tool_name.lower() in IGNORE_AS_TOOL:
            mapped = uri_to_name(uri)
            if mapped is None: continue   # link decorativo
            tool_name = mapped

        if not tool_name or tool_name.lower() in IGNORE_AS_TOOL:
            continue

        domain = find_domain_for_point(cx, cy)
        goal   = find_goal_for_point(cx, cy, goals)

        rows.append({"domain": domain, "goal": goal, "tool": tool_name, "url": uri})

    print(f"      {len(rows)} registros antes de deduplicacao.")

    df_tools = pd.DataFrame(rows, columns=["domain", "goal", "tool", "url"])
    df_tools = df_tools[~df_tools["tool"].str.lower().isin(IGNORE_AS_TOOL)]
    df_tools.drop_duplicates(subset=["domain", "goal", "tool"], inplace=True)
    df_tools.sort_values(["domain", "goal", "tool"], inplace=True)
    df_tools.reset_index(drop=True, inplace=True)

    print("[5/6] Exportando tools.csv...")
    df_tools.to_csv(CSV_TOOLS, index=False, encoding="utf-8")
    print(f"      {len(df_tools)} tools -> {CSV_TOOLS}")

    print("[6/6] Gerando tools_hierarchy.csv (DOMAIN / GOAL / TOOL destacados)...")
    df_hier = build_hierarchy_csv(df_tools)
    df_hier.to_csv(CSV_HIERARCHY, index=False, encoding="utf-8")
    print(f"      {len(df_hier)} linhas -> {CSV_HIERARCHY}")

    # --- Estatisticas ---
    n_domains = df_tools["domain"].nunique()
    n_goals   = df_tools["goal"].nunique()
    n_tools   = len(df_tools)
    all_uris  = {lk["uri"].strip() for lk in links}
    urls_pdf  = sum(1 for _, r in df_tools.iterrows() if r["url"].strip() in all_uris)

    print()
    print("=" * 62)
    print("RESUMO DA EXTRACAO")
    print("=" * 62)
    print(f"  Domains encontrados  : {n_domains}")
    print(f"  Goals encontrados    : {n_goals}")
    print(f"  Tools extraidas      : {n_tools}")
    print(f"  URLs do PDF          : {urls_pdf}")
    print(f"  URLs inferidas       : {n_tools - urls_pdf}")
    print("=" * 62)

    print()
    print("=== Hierarquia completa ===")
    for d_name in DOMAIN_ORDER:
        d_df = df_tools[df_tools["domain"] == d_name]
        if d_df.empty: continue
        g_list = df_hier[(df_hier["level"] == "GOAL") & (df_hier["domain"] == d_name)]["goal"].tolist()
        print(f"  {d_name} ({len(d_df)} tools)")
        for g_name in g_list:
            tc = len(d_df[d_df["goal"] == g_name])
            print(f"    -> {g_name} ({tc} tools)")

    doc.close()


if __name__ == "__main__":
    main()
