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
    
api_retriever = module.OpenSearchRetriever(
    client=os_client,
    embedding_function=llm_emb
)

index_paths_name = os.getenv('PATHS_INDEX_NAME')
index_components_name = os.getenv('COMPONENTS_INDEX_NAME')
index_vector_name = os.getenv('VECTORS_INDEX_NAME')
index_vector_paths_name = os.getenv('VECTORS_PATH_INDEX_NAME')
index_vector_components_name = os.getenv('VECTORS_COMPONENTS_INDEX_NAME')
def lambda_handler(event, context):
 
    index_vector_settings = ssm.get_parameter(Name=index_vector_name)['Parameter']['Value']
    index_paths_settings = ssm.get_parameter(Name=index_paths_name)['Parameter']['Value']
    index_components_settings = ssm.get_parameter(Name=index_components_name)['Parameter']['Value']
    
    try:
        # 인덱스 생성
        response = api_retriever.create_index(index_name= index_paths_name, index_mapping = index_paths_settings  )
        print(f"Index created: {response}")
        response = api_retriever.create_index(index_name= index_components_name, index_mapping = index_components_settings  )
        print(f"Index created: {response}")
        response = api_retriever.create_index(index_name= index_vector_paths_name, index_mapping = index_vector_settings  )
        print(f"Index created: {response}")
        response = api_retriever.create_index(index_name= index_vector_components_name, index_mapping = index_vector_settings  )
        print(f"Index created: {response}")
        
        responseMessage = {
            'PhysicalResourceId': [index_paths_name,index_components_name,index_vector_name],
            'Data': {
                'Message': f"Index {index_paths_name},{index_components_name},{index_vector_name} created successfully"
            }
        }
        return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(responseMessage)
            }
    except Exception as e:
        print(f"Error creating index: {str(e)}")
        raise Exception(f"Failed to create index: {str(e)}")
 