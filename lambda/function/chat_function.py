import boto3
import importlib.util
import os
import json
from typing import List, Tuple

import langchain_aws

from opensearchpy import OpenSearch, RequestsHttpConnection
from botocore.config import Config
from langchain.docstore.document import Document
from requests_aws4auth import AWS4Auth
from langchain.schema import Document
from langchain_core.messages import HumanMessage
from langchain.schema.output_parser import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_community.vectorstores import OpenSearchVectorSearch

ssm = boto3.client('ssm')
s3 = boto3.client('s3')

index_paths_name = os.getenv('PATHS_INDEX_NAME')
index_components_name = os.getenv('COMPONENTS_INDEX_NAME')
index_vector_paths_name = os.getenv('VECTORS_PATH_INDEX_NAME')
index_vector_components_name = os.getenv('VECTORS_COMPONENTS_INDEX_NAME')

opensearch_domain_endpoint = ssm.get_parameter(Name='opensearchdomain')['Parameter']['Value']
opensearch_user_password = ssm.get_parameter(Name='opensearchpassword')['Parameter']['Value']
opensearch_user_id = ssm.get_parameter(Name='opensearchid')['Parameter']['Value']

opensearch = boto3.client('opensearch')


http_auth = (opensearch_user_id, opensearch_user_password) # Master username, Master password

region="us-west-2"

boto3_bedrock_runtime = boto3.client("bedrock-runtime")
llm_emb = langchain_aws.BedrockEmbeddings( region_name=region, model_id="amazon.titan-embed-text-v2:0", 
                                       client=boto3_bedrock_runtime
)
model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
#model_id = "meta.llama3-70b-instruct-v1:0"

model_kwargs =  { 
    "max_tokens": 10000000,  # Claude-3 use “max_tokens” However Claud-2 requires “max_tokens_to_sample”.
    "temperature": 0.0,
#    "top_k": 250,
    "top_p": 1
#    "stop_sequences": ["\n\nHuman"],
}

llm_text = langchain_aws.ChatBedrock(
    client=boto3_bedrock_runtime,
    model_id=model_id,
    model_kwargs=model_kwargs,
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

    
path_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_paths_name,
    k=15, 
    embedding_function=llm_emb
)
vector_path_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_vector_paths_name,
    k=15,
    vector_search=vector_path_db,
    embedding_function=llm_emb
)
components_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_components_name,
    k=15, 
    embedding_function=llm_emb
)
vector_components_retriever = module.OpenSearchRetriever(
    client=os_client,
    index_name=index_vector_components_name,
    k=15,
    vector_search=vector_component_db,
    embedding_function=llm_emb
)

system_template = '''
You are an API expert. 
Your task is to analyze OpenAPI specifications provided by the user and generate accurate responses based on the information contained within these specifications. 
Follow these guidelines:
Analyze the OpenAPI Specification: 
    Carefully examine the details in the OpenAPI specification, including endpoints, methods, parameters, and response formats.
    
Provide Accurate Answers: 
    Use the information from the specification to answer user questions accurately. 
    Ensure your responses are clear and concise.
    
Acknowledge Uncertainty: 
    If you encounter a question or aspect of the specification that you do not fully understand or cannot find information on, respond with "I do not know" or indicate that the information is not available.
    
Maintain Professionalism: 
    Keep your responses professional and aligned with your role as an API expert.
    Clarify When Needed: If a user's question is unclear, ask for clarification to ensure you provide the most accurate answer possible.
    By following these instructions, you will assist users effectively by leveraging your expertise in API analysis and OpenAPI specifications. 
    This prompt ensures that the AI remains focused on its role as an API expert and provides reliable and professional assistance based on the given specifications.

User Question: {QUERY}

OpenAPI Paths:
{OPENAPI_PATHS}

OpenAPI Components:
{OPENAPI_COMPONENTS}
'''

human_template = '''
    {OPENAPI_COMPONENTS}
    {OPENAPI_PATHS}
    {QUERY}
'''
system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)
human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

chat_prompt = ChatPromptTemplate.from_messages([
    system_message_prompt,
    human_message_prompt
])
qa_chain = chat_prompt | llm_text | StrOutputParser() 

def lambda_handler(event, context):
    try:
        # API Gateway에서 전달된 body 파싱
        body = json.loads(event['body'])
        query = body['message']
        print(query)
        
        
        retrieval_vector_path = vector_path_retriever._get_relevant_documents(query)
        context_vector_path = []
        for doc in retrieval_vector_path:
            context_vector_path.append( json.dumps(json.loads(doc.page_content), ensure_ascii=False))

        # retrieval_path = path_retriever.get_path_with_resolved_components(query)
        # context_path = []
        # for doc in retrieval_path:
        #     context_path.append( json.dumps(json.loads(doc.page_content), ensure_ascii=False))
 
        print(context_vector_path) 
        context_components = components_retriever.get_path_with_resolved_components (query)
    
        print(context_components) 
    
        message = {
            # "OPENAPI_INFO" : json.dumps( JSON_object["info"], ensure_ascii=False),
            # "OPENAPI_SECURITY" : json.dumps(JSON_object["security"], ensure_ascii=False),
            # "OPENAPI_SERVER" : json.dumps(JSON_object["servers"], ensure_ascii=False),
            "OPENAPI_PATHS" : json.dumps( context_vector_path),
            "OPENAPI_COMPONENTS" : json.dumps( context_components, ensure_ascii=False),
            "QUERY": query
        }
        response = qa_chain.invoke(
            input={
                "OPENAPI_PATHS" : json.dumps( context_vector_path),
                "OPENAPI_COMPONENTS" : json.dumps( context_components, ensure_ascii=False),
                "QUERY": query
            },
            verbose=False
        )
        # response, contexts = qa_chain.invoke(
        #     query = message,
        #     verbose=False
        # )
 
        return {
            'statusCode': 200,
            'body': json.dumps({'response': response}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'  # CORS 설정
            }
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
