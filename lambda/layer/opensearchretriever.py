import logging
from langchain.docstore.document import Document
from opensearchpy import OpenSearch, RequestsHttpConnection, NotFoundError
from langchain.schema import BaseRetriever
from langchain_community.vectorstores import OpenSearchVectorSearch
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenSearchRetriever(BaseRetriever):
    client: OpenSearch
    embedding_function: Any
    alpha: float = Field(default=0.5)
    k: int = Field(default=10)
    vector_search: Optional[OpenSearchVectorSearch] = Field(default=None)
    index_name: str = Field(default="apispecification")
    text_field: str = Field(default="text")
    vector_field: str = Field(default="vector")
    metadata_field: str = Field(default="metadata")
        # index_paths_name: str = Field(default="paths")
        # index_vector_paths_name: str = Field(default="vectors_paths")
        # index_components_name: str = Field(default="components")
        # index_vector_components_name: str = Field(default="vector_components")
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **data):
        super().__init__(**data)
        self.embedding_function = data["embedding_function"]
        self.alpha = data.get("alpha", 0.5)
        self.k = data.get("k", 15)
        self.client = data.get("client", None)
        self.vector_search = data.get("vector_search", None)
        self.index_name = data.get("index_name", "apispecification")
        self.text_field = data.get("text_field","text")
        self.vector_field = data.get("vector_field","vector")
        self.metadata_field = data.get("metadata_field","metadata")           # self.vector_paths_db = data.get("vector_paths_db")
        
        # self.vector_components_db = data.get("vector_components_db")
        # self.index_paths_name = data.get("index_paths_name", "paths")
        # self.index_vector_paths_name = data.get("index_vector_paths_name", "vectors_paths")
        # self.index_components_name = data.get("index_components_name", "components")
        # self.index_vector_components_name = data.get("index_vector_components_name", "vector_components")
        # add vector DB OpenSearchVectorSearch
        
    def _get_relevant_documents(self, query: str) -> List[Document]:
        try:
            keyword_query = {
                "query": {
                    "match": {
                        self.text_field: query
                    }
                }
            }
            print("keyword query")
            keyword_results = self.client.search(
                index=self.index_name,
                body=keyword_query,
                size=self.k
            )
            print("vector query1")
            # 벡터 검색 부분 수정
            
            
            vector_results = self.vector_search.similarity_search(query=query, k=self.k)
            print("vector query2")
            combined_docs = self._combine_and_rerank(keyword_results, vector_results) 
            print("vector query3")

            return self._add_parent_documents(combined_docs)
            print("vector query2")
    
        except Exception as e:
            logger.error(f"Error in _get_relevant_documents: {e}")
            return []

    def _combine_and_rerank(self, keyword_results: Dict, vector_results: List[Document]) -> List[Document]:
        doc_scores = {}
        for hit in keyword_results['hits']['hits']:
            doc_id = hit['_id']
            score = hit['_score'] * self.alpha
            doc_scores[doc_id] = {'score': score, 'doc': hit['_source']}
        
        for i, doc in enumerate(vector_results):
            doc_id = doc.metadata.get('id', f"vector_{i}")
            score = (1 - self.alpha) * (1 / (i + 1))
            if doc_id in doc_scores:
                doc_scores[doc_id]['score'] += score
            else:
                doc_scores[doc_id] = {'score': score, 'doc': {self.text_field: doc.page_content, self.metadata_field: doc.metadata}}
        
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        return [Document(page_content=item[1]['doc'][self.text_field], metadata=item[1]['doc'].get(self.metadata_field, {})) for item in sorted_docs[:self.k]]

    def _add_parent_documents(self, docs: List[Document]) -> List[Document]:
        result = []
        for doc in docs:
            result.append(doc)
            parent_id = doc.metadata.get('parent_id')
            if parent_id:
                parent_doc = self._get_parent_document(parent_id)
                if parent_doc:
                    result.append(parent_doc)
        return result

    def _get_parent_document(self, parent_id: str) -> Optional[Document]:
        try:
            response = self.client.get(index=self.index_name, id=parent_id)
            source = response['_source']
            return Document(
                page_content=source[self.text_field],
                metadata={**source.get(self.metadata_field, {}), 'is_parent': True}
            )
        except NotFoundError:
            logger.warning(f"Parent document with id {parent_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error retrieving parent document: {e}")
            return None

    def add_documents(self, documents: List[Document], parent_documents: Optional[Dict[str, Document]] = None):
        try:
            for doc in documents:
                vector = self.embedding_function.embed_query(doc.page_content)
                body = {
                    self.text_field: doc.page_content,
                    self.vector_field: vector,
                    self.metadata_field: doc.metadata
                }
                
                if parent_documents and doc.metadata.get('id') in parent_documents:
                    parent_doc = parent_documents[doc.metadata['id']]
                    body['parent'] = {
                        'id': parent_doc.metadata.get('id'),
                        self.text_field: parent_doc.page_content,
                        self.metadata_field: parent_doc.metadata
                    }
                    body[self.metadata_field]['parent_id'] = parent_doc.metadata.get('id')
                
                self.client.index(index=self.index_name, body=body, id=doc.metadata.get('id'))
            
            self.client.indices.refresh(index=self.index_name)
        except Exception as e:
            logger.error(f"Error adding documents: {e}")

    def create_index(self, index_name: str, index_mapping: Dict):
        try:
            if self.client.indices.exists(index=index_name):
                logger.info(f"Index '{index_name}' already exists. Deleting it.")
                self.client.indices.delete(index=index_name)
            response = self.client.indices.create(index=index_name, body=index_mapping)
            logger.info(f"Index '{index_name}' created successfully.")
        except Exception as e:
            logger.error(f"Error creating index: {e}")

    def search_by_key(self, key: str) -> List[Dict]:
        try:
            query = {
                "query": {
                    "term": {
                        "key": key
                    }
                },
                "size": 100
            }
            response = self.client.search(body=query, index=self.index_name)
        
            hits = response['hits']['hits']
            if hits:
                return [hit['_source'] for hit in hits]
            else:
                logger.info(f"No documents found for key: {key}")
                return []
        except Exception as e:
            logger.error(f"Error searching by key: {e}")
            return []
    
    def bulk_write_paths(self, documents: Dict):
        try:
            for path, methods in documents["paths"].items():
                doc = {
                    "key": path,
                    "info": documents["info"],
                    "methods": self._prepare_methods(methods)
                }
                doc_id = path
                response = self.client.index(index=self.index_name, id=doc_id, body=doc, refresh=True)
                logger.info(f"Inserted document for path {path}: {response['result']}")
        except Exception as e:
            logger.error(f"Error in bulk_write_paths: {e}")

    def _prepare_methods(self, methods: Dict) -> Dict:
        prepared_methods = {}
        for method, details in methods.items():
            prepared_method = details.copy()
            if 'parameters' in prepared_method:
                prepared_method['parameters'] = [self._prepare_parameter(param) for param in prepared_method['parameters']]
            prepared_methods[method] = prepared_method
        return prepared_methods

    def _prepare_parameter(self, parameter: Dict) -> Dict:
        prepared_param = parameter.copy()
        if 'example' in prepared_param:
            prepared_param['example'] = str(prepared_param['example'])
        return prepared_param

    def bulk_write_components(self, documents: Dict):
        try:
            component_types = ["schemas", "responses", "parameters", "examples", "requestBodies", "headers", "securitySchemes", "links", "callbacks"]
            
            for component_type in component_types:
                if component_type in documents["components"]:
                    for key, value in documents["components"][component_type].items():
                        doc = {
                            "key": key,
                            "value": value,
                            "component_type": component_type,
                        }
                        doc_id = f"{component_type}_{key}"
                        response = self.client.index(index=self.index_name, id=doc_id, body=doc, refresh=True)
                        logger.info(f"Inserted document for {component_type} {key}: {response['result']}")
        except Exception as e:
            logger.error(f"Error in bulk_write_components: {e}")

    # def apispecification_write(self, documents: Dict):
    #     self.bulk_write_paths(documents)
    #     self.bulk_write_components(documents)

    def bulk_write_testcases(self, documents: List[Dict]):
        try:
            for obj in documents:
                doc = {
                    "key": obj["EndPoint"],
                    "method": obj["Method"],
                    "host": obj["Host"],
                    "endpoint": obj["EndPoint"],
                    "precondition": obj["Precondition"],
                    "verification_procedure": obj["VerificationProcedure"],
                    "expected_result": obj["ExpectedResult"],
                    "priority": obj["Priority"],
                    "test_result": obj["TestResult"],
                    "jira": obj["jira"],
                    "remarks": obj["Remarks"],
                    "response": obj["RESPONSE"]
                }
                doc_id = f"{obj['Host']}_{obj['EndPoint']}_{obj['Method']}"
                response = self.client.index(index=self.index_name, id=doc_id, body=doc, refresh=True)
                logger.info(f"Inserted document for testcase {doc_id}: {response['result']}")
        except Exception as e:
            logger.error(f"Error in bulk_write_testcases: {e}")

    def resolve_refs(self, schema: Dict, resolved_schemas: Optional[Dict] = None) -> Dict:
        if resolved_schemas is None:
            resolved_schemas = {schema["key"]: schema}
        if isinstance(schema, dict):
            for key, value in schema.items():
                if key == "$ref" and isinstance(value, str):
                    ref_key = value.split('/')[-1]
                    if ref_key not in resolved_schemas:
                        ref_schema = self.get_schema_by_key(ref_key)
                        resolved_schemas[ref_key] = ref_schema
                        self.resolve_refs(ref_schema, resolved_schemas)
                    schema[key] = resolved_schemas[ref_key]
                elif isinstance(value, (dict, list)):
                    self.resolve_refs(value, resolved_schemas)
        elif isinstance(schema, list):
            for item in schema:
                self.resolve_refs(item, resolved_schemas)
        return resolved_schemas

    def get_schema_by_key(self, key: str) -> Optional[Dict]:
        try:
            query = {
                "query": {
                    "term": {"key": key}
                },
                "size": 100
            }
            response = self.client.search(index=self.index_name, body=query)
            if response['hits']['hits']:
                return response['hits']['hits'][0]['_source']
            return None
        except Exception as e:
            logger.error(f"Error in get_schema_by_key: {e}")
            return None

    def get_fully_resolved_schema(self, initial_key: str) -> Optional[str]:
        try:
            initial_schema = self.get_schema_by_key(initial_key)
            if initial_schema:
                resolved_schema = self.resolve_refs(initial_schema)
                return json.dumps(list(resolved_schema.values()), indent=2, ensure_ascii=False)
            return None
        except Exception as e:
            logger.error(f"Error in get_fully_resolved_schema: {e}")
            return None

    def resolve_component_refs(self, obj: Union[Dict, List], resolved_components: Dict):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "$ref" and isinstance(value, str):
                    ref_key = value.split('/')[-1]
                    if ref_key not in resolved_components:
                        component = self.get_schema_by_key(ref_key)
                        if component:
                            resolved_components[ref_key] = component
                            self.resolve_component_refs(component, resolved_components)
                elif isinstance(value, (dict, list)):
                    self.resolve_component_refs(value, resolved_components)
        elif isinstance(obj, list):
            for item in obj:
                self.resolve_component_refs(item, resolved_components)

    def get_path_with_resolved_components(self, path: str) -> Optional[Dict]:
        try:
            path_doc = self.get_schema_by_key(path)
            
            if not path_doc:
                logger.warning(f"No path found for: {path}")
                return None
            
            resolved_components = {}
            
            self.resolve_component_refs(path_doc, resolved_components)
            
            return {
                "path": path_doc,
                "components": list(resolved_components.values())
            }
        except Exception as e:
            logger.error(f"Error in get_path_with_resolved_components: {e}")
            return None
