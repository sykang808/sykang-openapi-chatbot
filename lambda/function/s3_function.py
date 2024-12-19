import boto3
import json
from typing import List, Tuple
from opensearchpy import OpenSearch, RequestsHttpConnection
import boto3
from botocore.config import Config
import langchain_aws
from langchain.docstore.document import Document
import importlib.util
from requests_aws4auth import AWS4Auth
import os
from langchain_community.vectorstores import OpenSearchVectorSearch


ssm = boto3.client('ssm')
s3 = boto3.client('s3')
opensearch_domain_endpoint = ssm.get_parameter(Name='opensearchdomain')['Parameter']['Value']
opensearch_user_password = ssm.get_parameter(Name='opensearchpassword')['Parameter']['Value']
opensearch_user_id = ssm.get_parameter(Name='opensearchid')['Parameter']['Value']
http_auth = (opensearch_user_id, opensearch_user_password) # Master username, Master password

opensearch = boto3.client('opensearch')

region="us-west-2"

boto3_bedrock_runtime = boto3.client("bedrock-runtime")
llm_emb = langchain_aws.BedrockEmbeddings( region_name=region, model_id="amazon.titan-embed-text-v2:0", 
                                       client=boto3_bedrock_runtime
)

credentials = boto3.Session().get_credentials()
# awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, 'es', session_token=credentials.token)
 
os_client = OpenSearch(
    hosts=[
        {'host': opensearch_domain_endpoint.replace("https://", ""),
         'port': 443
        }
    ],
    http_auth=http_auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

spec = importlib.util.spec_from_file_location("OpenSearchRetriever", "/opt/python/opensearchretriever.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
    

index_paths_name = os.getenv('PATHS_INDEX_NAME')
index_components_name = os.getenv('COMPONENTS_INDEX_NAME')
index_vector_paths_name = os.getenv('VECTORS_PATH_INDEX_NAME')
index_vector_components_name = os.getenv('VECTORS_COMPONENTS_INDEX_NAME')

vector_path_db = OpenSearchVectorSearch(
    index_name=index_vector_paths_name,
    opensearch_url=f"https://{opensearch_domain_endpoint}",
    embedding_function=llm_emb,
    http_auth=http_auth, # http_auth
    is_aoss=False,
    engine="faiss",
    space_type="l2",
    bulk_size=100000,
    timeout=60
)
vector_component_db = OpenSearchVectorSearch(
    index_name=index_vector_components_name,
    opensearch_url=f"https://{opensearch_domain_endpoint}",
    embedding_function=llm_emb,
    http_auth=http_auth, # http_auth
    is_aoss=False,
    engine="faiss",
    space_type="l2",
    bulk_size=100000,
    timeout=60
)


paths_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_paths_name,
    embedding_function=llm_emb
)
components_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_components_name,
    embedding_function=llm_emb
)
paths_vector_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_vector_paths_name,
    embedding_function=llm_emb,
    vector_search=vector_path_db,
)
components_vector_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_vector_components_name,
    embedding_function=llm_emb,
    vector_search=vector_component_db
)

def lambda_handler(event, context):
    
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    
# # 'apispecification/' 폴더의 파일만 처리
#     if key.startswith('apispecification/'):    
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj['Body'].read().decode('utf-8')

    print( "Data validate and preprocess")
    # 데이터 검증 및 전처리
    data = data.strip()
    JSON_object = json.loads(data)
  
    # JSON 객체 처리
    for key in JSON_object:
        JSON_string = json.dumps(key)
        print(JSON_string)

    child_path_docs = []

    for i, obj in enumerate(JSON_object["paths"]):
        schema = {}
        schema["info"] = JSON_object["info"] if JSON_object.get("info") else None
        schema["servers"] = JSON_object["servers"] if JSON_object.get("servers") else None
        schema["security"] = JSON_object["security"] if JSON_object.get("security") else None
        schema[obj] = JSON_object["paths"][obj] if JSON_object["paths"].get(obj) else None

        # Remove keys with None values
        schema = {k: v for k, v in schema.items() if v is not None}

        # Only create a Document if schema is not empty
        if schema:
            doc = Document(page_content=json.dumps(schema, ensure_ascii=False))
            child_path_docs.append(doc)
        
    child_components_docs = []
    if "components" in JSON_object:
        for i, obj in enumerate(JSON_object["components"].get("schemas", {})):
            schema = {}
            schema["securitySchemes"] = JSON_object["components"].get("securitySchemes") if JSON_object["components"].get("securitySchemes") else None
            schema["basicAuth"] = JSON_object["components"].get("basicAuth") if JSON_object["components"].get("basicAuth") else None
            schema[obj] = JSON_object["components"]["schemas"].get(obj) if JSON_object["components"]["schemas"].get(obj) else None

            # Remove keys with None values
            schema = {k: v for k, v in schema.items() if v is not None}

            # Only create a Document if schema is not empty
            if schema:
                doc = Document(page_content=json.dumps(schema, ensure_ascii=False))
                child_components_docs.append(doc)
    else:
        print("No components found in the JSON object.")

    
    print( "Start OpenSearch")
    paths_vector_retriever.add_documents(child_path_docs)
    paths_retriever.bulk_write_paths ( JSON_object )

    components_vector_retriever.add_documents(child_components_docs)    
    components_retriever.bulk_write_components ( JSON_object )
    print( "Fin OpenSearch")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
# # 'testcase/' 폴더의 파일만 처리
#     if key.startswith('testcase/'):
#         obj = s3.get_object(Bucket=bucket, Key=key)
#         data = obj['Body'].read().decode('utf-8')
#         print( data )
#         print( "Data validate and preprocess")
#         # 데이터 검증 및 전처리
#         data = data.strip()
#         JSON_object = json.loads(data)
#         print( JSON_object)
#         # JSON 객체 처리
#         for key in JSON_object:
#             JSON_string = json.dumps(key)
#             print(JSON_string)

#         child_path_docs = []

#         for i, obj in enumerate(JSON_object["paths"]):
#             schema = {}
#             schema[obj] = JSON_object["paths"][obj]
#             doc =  Document(page_content=json.dumps(schema, ensure_ascii=False))
#             child_path_docs.append(doc)
        
#         print( "Start OpenSearch")
#         api_retriever.apispecification_write( JSON_object )
#         print( "Fin OpenSearch")
        
#         return {
#             'statusCode': 200,
#             'body': json.dumps('Hello from Lambda!')
#         }        