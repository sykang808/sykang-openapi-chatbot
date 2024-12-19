# Chatbot for OpenAPI Specification

## 프로젝트 개요

이 프로젝트는 AWS CDK를 사용하여 다음과 같은 클라우드 리소스를 배포합니다:

1. **API Gateway**: REST API를 제공하며, Lambda와 연동됩니다.
2. **Fargate 서비스**: Streamlit 기반의 프론트엔드 애플리케이션을 실행합니다.
3. **SSM Parameter Store**: API Gateway URL을 저장하고 Fargate 서비스에서 이를 참조합니다.
4. **OpenSearch**: Nori Plugin을 사용하여 텍스트 분석을 지원합니다. (Nori Plugin은 수동으로 설치해야 합니다.)
5. **Lambda 함수**: OpenSearch 인덱스를 생성하는 데 사용됩니다.

---

## 사전 요구사항

### 필수 도구

- [AWS CLI](https://aws.amazon.com/cli/) (설치 및 인증 필요)
- [Node.js](https://nodejs.org/) (CDK를 실행하기 위한 최신 LTS 버전 권장)
- [Docker](https://www.docker.com/) (Fargate 컨테이너 이미지를 빌드하기 위해 필요)
- [Python](https://www.python.org/) (Lambda 함수 및 Streamlit 애플리케이션 실행)

### AWS 권한

배포를 위해 다음 권한이 필요합니다:

- S3, ECR, ECS, Lambda, API Gateway, OpenSearch, SSM Parameter Store에 대한 관리 권한

---

## 주요 구성 요소

### 1. API Gateway Stack

- **역할**: RESTful API를 제공하며 Lambda와 연동됩니다.
- **출력**: API Gateway URL이 SSM Parameter Store에 저장됩니다.

### 2. Fargate Stack

- **역할**: Streamlit 기반의 프론트엔드 애플리케이션을 실행합니다.
- **구성**:
  - Docker 이미지를 ARM64 아키텍처로 빌드하여 Fargate에서 실행
  - SSM Parameter Store에서 API Gateway URL을 읽어 환경 변수로 전달
- **출력**: ALB의 DNS 이름이 출력됩니다.

### 3. OpenSearch

- **역할**: 텍스트 분석 및 검색 기능 제공
- **주의사항**:
  - Nori Plugin은 수동으로 설치해야 합니다.
  - 설치 후 Lambda를 통해 인덱스를 생성해야 합니다.

---

## 배포 가이드

### 1. 프로젝트 클론 및 의존성 설치

```bash
git clone https://github.com/sykang808/sykang-openapi-chatbot.git
cd sykang-openapi-chatbot
npm install
```

---

### 2. CDK 환경 부트스트랩

AWS CDK를 처음 사용하는 경우, 배포 환경을 부트스트랩해야 합니다:

```bash
cdk bootstrap
```

---

### 3. 스택 배포

#### Step 1: API Gateway 스택 배포

```bash
cdk deploy --all
```

#### Step 2: OpenSearch Nori 설치

- Amazon 콘솔의 Opensearch에서 wwapiopensearch-xxxx로 생성된 클러스터를 선택합니다.
- 패키지에서 nori플러그인을 수동으로 설치합니다.

#### Step 3: 인덱스 생성

- 설치가 완료된 후 CloudFormation에서 WwapiStack을 선택합니다.
- Output에서 ResetIndexApiUrl의 주소를 이동합니다. 아래와 같은 결과가 나오면 인덱스가 생성된 것입니다.

#### Step 4: S3

- CloudFormation에서 WwapiStack을 선택합니다.
- 출력의 s3 버킷으로 이동하여 버킷에 openspecification json을 올립니다.
- 자동으로 RAG에 파싱하여 저장됩니다.

---

## 테스트 가이드

- CloudFormation에서 WwapiFrontEndStack을 선택합니다.
- 출력의 FargateAppUrl 주소로 접속합니다.

---

## 디버깅 및 문제 해결

1. **SSM Parameter Store 접근 오류 (`AccessDeniedException`)**

- Fargate Task Role에 `ssm:GetParameter` 권한이 있는지 확인하세요.

2. **API 요청 실패**

- API Gateway의 URL이 올바르게 설정되었는지 확인하세요.
- CloudWatch Logs에서 Lambda 오류를 확인하세요.

3. **OpenSearch 연결 오류**

- VPC 내 보안 그룹 및 서브넷 구성을 확인하세요.
- Lambda와 OpenSearch가 동일한 VPC에 있는지 확인하세요.

4. **Nori Plugin 미작동**

- Nori Plugin이 올바르게 설치되었는지 확인하고 OpenSearch 노드를 재시작하세요.

---

## 주요 출력값

1. **API Gateway URL**:
   - SSM Parameter Store에 저장 (`/wwapi/api-gateway-url`).
2. **ALB URL**:
   - Fargate 서비스의 DNS 이름이 출력됩니다.

---

## 추가 참고 사항

1. **비용 관리**

- 배포된 리소스는 AWS 요금이 발생하므로 사용하지 않을 경우 삭제하세요:
  ```
  cdk destroy --all
  ```

2. **확장 가능성**

- 이 프로젝트는 확장 가능한 아키텍처로 설계되었습니다.
- 추가 기능(예: 인증, 데이터베이스)을 쉽게 통합할 수 있습니다.

3. **절대 프로덕션에 사용하지 마세요**

- 이 프로젝트는 보안과 비용을 전혀 고려하지 않았습니다.
- 실제 프로덕션에 사용했을 경우 생기는 문제에 대해선 책임지지 않습니다.

---

Happy Deploying! 🚀
