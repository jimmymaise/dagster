import json
import os
import pathlib
import pickle
import subprocess
import tempfile

import requests
from dagster import (
    AssetExecutionContext,
    AssetSelection,
    Config,
    Definitions,
    EnvVar,
    RunRequest,
    SensorResult,
    StaticPartitionsDefinition,
    asset,
    define_asset_job,
    sensor,
)
from dagster_openai import OpenAIResource
from filelock import FileLock
from langchain.chains.qa_with_sources import stuff_prompt
from langchain.chat_models.openai import ChatOpenAI
from langchain.docstore.document import Document
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.schema.output_parser import StrOutputParser
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores.faiss import FAISS

docs_partitions_def = StaticPartitionsDefinition(["guides", "integrations"])

SEARCH_INDEX_FILE = "search_index.pickle"

SUMMARY_TEMPLATE = """
Content: {content}
Source: {source}
"""


@asset(partitions_def=docs_partitions_def)
def source_docs(context: AssetExecutionContext):
    return list(get_github_docs("dagster-io", "dagster", context.partition_key))


@asset(compute_kind="OpenAI", partitions_def=docs_partitions_def)
def search_index(context: AssetExecutionContext, openai: OpenAIResource, source_docs):
    source_chunks = []
    splitter = CharacterTextSplitter(separator=" ", chunk_size=1024, chunk_overlap=0)
    for source in source_docs:
        context.log.info(source)
        for chunk in splitter.split_text(source.page_content):
            source_chunks.append(Document(page_content=chunk, metadata=source.metadata))

    with openai.get_client(context) as client:
        search_index = FAISS.from_documents(
            source_chunks, OpenAIEmbeddings(client=client.embeddings)
        )

    with FileLock(SEARCH_INDEX_FILE):
        if os.path.getsize(SEARCH_INDEX_FILE) > 0:
            with open(SEARCH_INDEX_FILE, "rb") as f:
                serialized_search_index = pickle.load(f)
            cached_search_index = FAISS.deserialize_from_bytes(
                serialized_search_index, OpenAIEmbeddings()
            )
            search_index.merge_from(cached_search_index)

        with open(SEARCH_INDEX_FILE, "wb") as f:
            pickle.dump(search_index.serialize_to_bytes(), f)


class OpenAIConfig(Config):
    model: str
    question: str


@asset(compute_kind="OpenAI")
def completion(context: AssetExecutionContext, openai: OpenAIResource, config: OpenAIConfig):
    with open(SEARCH_INDEX_FILE, "rb") as f:
        serialized_search_index = pickle.load(f)
    search_index = FAISS.deserialize_from_bytes(serialized_search_index, OpenAIEmbeddings())
    with openai.get_client(context) as client:
        prompt = stuff_prompt.PROMPT
        model = ChatOpenAI(client=client.chat.completions, model=config.model, temperature=0)
        summaries = [
            SUMMARY_TEMPLATE.format(content=doc.page_content, source=doc.metadata["source"])
            for doc in search_index.similarity_search(config.question, k=4)
        ]
        output_parser = StrOutputParser()
        chain = prompt | model | output_parser
        context.log.info(chain.invoke({"summaries": summaries, "question": config.question}))


def get_wiki_data(title, first_paragraph_only):
    url = f"https://en.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&explaintext=1&titles={title}"
    if first_paragraph_only:
        url += "&exintro=1"
    data = requests.get(url).json()
    return Document(
        page_content=next(iter(data["query"]["pages"].values()))["extract"],
        metadata={"source": f"https://en.wikipedia.org/wiki/{title}"},
    )


def get_github_docs(repo_owner, repo_name, category):
    with tempfile.TemporaryDirectory() as d:
        subprocess.check_call(
            f"git clone --depth 1 https://github.com/{repo_owner}/{repo_name}.git .",
            cwd=d,
            shell=True,
        )
        git_sha = (
            subprocess.check_output("git rev-parse HEAD", shell=True, cwd=d).decode("utf-8").strip()
        )
        docs_path = pathlib.Path(os.path.join(d, "docs/content", category))
        markdown_files = list(docs_path.glob("*/*.md")) + list(docs_path.glob("*/*.mdx"))
        for index, markdown_file in enumerate(markdown_files):
            with open(markdown_file, "r") as f:
                relative_path = markdown_file.relative_to(docs_path)
                github_url = (
                    f"https://github.com/{repo_owner}/{repo_name}/blob/{git_sha}/{relative_path}"
                )
                yield Document(page_content=f.read(), metadata={"source": github_url})


search_index_job = define_asset_job(
    "search_index_job",
    AssetSelection.keys("source_docs", "search_index"),
    partitions_def=docs_partitions_def,
)


question_job = define_asset_job(
    name="question_job",
    selection=AssetSelection.keys(["completion"]),
)


@sensor(job=question_job)
def question_sensor(context):
    PATH_TO_QUESTIONS = os.path.join(os.path.dirname(__file__), "../../", "data/questions")

    previous_state = json.loads(context.cursor) if context.cursor else {}
    current_state = {}
    runs_to_request = []

    for filename in os.listdir(PATH_TO_QUESTIONS):
        file_path = os.path.join(PATH_TO_QUESTIONS, filename)
        if filename.endswith(".json") and os.path.isfile(file_path):
            last_modified = os.path.getmtime(file_path)

            current_state[filename] = last_modified

            if filename not in previous_state or previous_state[filename] != last_modified:
                with open(file_path, "r") as f:
                    request_config = json.load(f)

                    runs_to_request.append(
                        RunRequest(
                            run_key=f"adhoc_request_{filename}_{last_modified}",
                            run_config={"ops": {"completion": {"config": {**request_config}}}},
                        )
                    )

    return SensorResult(run_requests=runs_to_request, cursor=json.dumps(current_state))


defs = Definitions(
    assets=[source_docs, search_index, completion],
    jobs=[search_index_job, question_job],
    resources={
        "openai": OpenAIResource(api_key=EnvVar("OPENAI_API_KEY")),
    },
    sensors=[question_sensor],
)
