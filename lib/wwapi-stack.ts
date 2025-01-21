import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambda_events from 'aws-cdk-lib/aws-lambda-event-sources';
import * as opensearchservice from 'aws-cdk-lib/aws-opensearchservice';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as python from '@aws-cdk/aws-lambda-python-alpha';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as triggers from 'aws-cdk-lib/triggers';

import * as cr from 'aws-cdk-lib/custom-resources';
import * as fs from 'fs';
import * as path from 'path';

export class WwapiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

 
    const bucket = new s3.Bucket(this, 'WWAPI-Bucket', {
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true
    });

    const sharedRole = new iam.Role(this, 'SharedLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'Shared role for multiple Lambda functions',
    });

    // Lambda 레이어 생성
    const commonLayer = new python.PythonLayerVersion(this, 'CommonLayer', {
      entry: 'lambda/layer',  // 레이어 코드가 있는 디렉토리
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
      description: 'Common libraries for Lambda functions',
    });
    const vector_path_index_name = 'vector_paths';
    const vector_components_index_name = 'vector_components';
    const path_index_name = 'paths';
    const path_settingsFilePath = './json/index_paths.json';
    const path_settings = fs.readFileSync(path_settingsFilePath, 'utf8');
    const path_parameter = new ssm.StringParameter(this, 'WWAPI-Path-Parameter', {
      parameterName: path_index_name,
      stringValue: path_settings,
      tier: ssm.ParameterTier.ADVANCED
    });

    const components_index_name = 'components';
    const components_settingsFilePath = './json/index_components.json';
    const components_settings = fs.readFileSync(components_settingsFilePath, 'utf8');
    const components_parameter = new ssm.StringParameter(this, 'WWAPI-Components-Parameter', {
      parameterName: components_index_name,
      stringValue: components_settings,
      tier: ssm.ParameterTier.ADVANCED
    });

    const vector_index_name = 'vector';
    const vector_settingsFilePath = './json/index_vector.json';
    const vector_settings = fs.readFileSync(vector_settingsFilePath, 'utf8');
    const vector_parameter = new ssm.StringParameter(this, 'WWAPI-Vector-Parameter', {
      parameterName: vector_index_name,
      stringValue: vector_settings,
      tier: ssm.ParameterTier.ADVANCED
    });
    // Opensearch ID,Password
    const opensearch_account = 'raguser';
    const opensearch_passwd = 'Test1234!';
    const opensearchpassword = new ssm.StringParameter(this, 'WWAPI-OpenSearch-Password', {
      parameterName: 'opensearchpassword',
      stringValue:opensearch_passwd
    });
    const opensearchid = new ssm.StringParameter(this, 'WWAPI-OpenSearch-ID', {
      parameterName: 'opensearchid',
      stringValue: opensearch_account
    });
    // create lambda function with python, add lambda log, metric, trace
    const lambdaFn = new lambda.Function(this, 'WWAPI-Lambda', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 's3_function.lambda_handler',
      code: lambda.Code.fromAsset('lambda/function'),
      logRetention: cdk.aws_logs.RetentionDays.ONE_DAY,
      tracing: lambda.Tracing.ACTIVE,
      layers: [commonLayer],  // 생성한 레이어 추가
      role:sharedRole,
      timeout: cdk.Duration.seconds(300), // 타임아웃 설정 (300초)
      environment: {
        PATHS_INDEX_NAME: path_index_name,
        COMPONENTS_INDEX_NAME: components_index_name,
        VECTORS_INDEX_NAME: vector_index_name,
        VECTORS_PATH_INDEX_NAME: vector_path_index_name,
        VECTORS_COMPONENTS_INDEX_NAME: vector_components_index_name
      },
    });
    //create trigger for lambda function with s3 add,update object
    lambdaFn.addEventSource(new lambda_events.S3EventSource(bucket, {
      events: [s3.EventType.OBJECT_CREATED]
    }));

    // grant lambda function read access to s3 bucket
    bucket.grantRead(sharedRole);

    sharedRole.addToPolicy(new cdk.aws_iam.PolicyStatement({
      actions: ['es:ESHttp*'],
      resources: ['*']
    }));
    sharedRole.addToPolicy(new iam.PolicyStatement({
      actions: ['es:ESHttp*'],
      resources: ['*']
    }));
    sharedRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['kms:Decrypt'],
      resources: ['*'], // 특정 KMS 키 ARN으로 제한 가능
    }));
    sharedRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'));
    // 환경 변수 접근을 위한 KMS 권한 추가
    // Bedrock 전체 권한 정책 생성
    const bedrockPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:*'],
      resources: ['*'],
    });
    // Lambda 함수에 Bedrock 권한 추가
    sharedRole.addToPolicy(bedrockPolicy);

    const os_lambdaFn = new lambda.Function(this, 'IndexHandler-Lambda', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'os_index_function.lambda_handler',
      code: lambda.Code.fromAsset('lambda/function'),
      logRetention: cdk.aws_logs.RetentionDays.ONE_DAY,
      tracing: lambda.Tracing.ACTIVE,
      layers: [commonLayer],  // 생성한 레이어 추가
      timeout: cdk.Duration.seconds(300), // 타임아웃 설정 (300초)
      environment: {
        PATHS_INDEX_NAME: path_index_name,
        COMPONENTS_INDEX_NAME: components_index_name,
        VECTORS_INDEX_NAME: vector_index_name,
        VECTORS_PATH_INDEX_NAME: vector_path_index_name,
        VECTORS_COMPONENTS_INDEX_NAME: vector_components_index_name
      },
      role:sharedRole
    });
 
    path_parameter.grantRead(os_lambdaFn);
    components_parameter.grantRead(os_lambdaFn);
    vector_parameter.grantRead(os_lambdaFn);


    // Add OpenSearch
    const domain = new opensearchservice.Domain(this, 'WWAPI-OpenSearch', {
      version: opensearchservice.EngineVersion.OPENSEARCH_2_15,
      capacity: {
        multiAzWithStandbyEnabled: false,
        masterNodes: 2,
        masterNodeInstanceType: 'm6g.large.search',
        dataNodes: 2,
        dataNodeInstanceType: 'm6g.large.search',
      },
      fineGrainedAccessControl: {
        masterUserName: opensearch_account,
        // masterUserPassword: cdk.SecretValue.secretsManager('opensearch-private-key'),
        masterUserPassword:cdk.SecretValue.unsafePlainText(opensearch_passwd)
      },
      // fineGrainedAccessControl: {
      //  masterUserArn: lambdaFn.role?.roleArn,
      // },
      zoneAwareness: {
        enabled: false,
        availabilityZoneCount: 2,
      },
      ebs: {
        volumeSize: 10,
      },
      nodeToNodeEncryption: true,
      encryptionAtRest: {
        enabled: true,
      },
      enforceHttps: true,
      useUnsignedBasicAuth: true
    });

    //add system manager parameter store, opensearch domain, opensearch id, opensearch password
    const opensearchdomain = new ssm.StringParameter(this, 'WWAPI-OpenSearch-Domain', {
      parameterName: 'opensearchdomain',
      stringValue: domain.domainEndpoint
    });
    
    opensearchdomain.grantRead(lambdaFn);
    domain.grantReadWrite(lambdaFn);
    domain.grantIndexReadWrite('*', lambdaFn);
 
    
    opensearchdomain.grantRead(os_lambdaFn);
    domain.grantReadWrite(os_lambdaFn);
    domain.grantIndexReadWrite('*', os_lambdaFn);

    
    // Lambda 함수 생성
    const chatbotFunction = new lambda.Function(this, 'ChatbotFunction', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'chat_function.lambda_handler',
      logRetention: cdk.aws_logs.RetentionDays.ONE_DAY,
      tracing: lambda.Tracing.ACTIVE,
      layers: [commonLayer], 
      code: lambda.Code.fromAsset('lambda/function'),
      role:sharedRole,
      timeout: cdk.Duration.seconds(300), // 타임아웃 설정 (300초)
      environment: {
        PATHS_INDEX_NAME: path_index_name,
        COMPONENTS_INDEX_NAME: components_index_name,
        VECTORS_INDEX_NAME: vector_index_name,
        VECTORS_PATH_INDEX_NAME: vector_path_index_name,
        VECTORS_COMPONENTS_INDEX_NAME: vector_components_index_name
      },
    });

    opensearchdomain.grantRead(chatbotFunction);
    domain.grantReadWrite(chatbotFunction);
    domain.grantIndexReadWrite('*', chatbotFunction);   
    opensearchpassword.grantRead(chatbotFunction);
    opensearchid.grantRead(chatbotFunction);  
    opensearchpassword.grantRead(lambdaFn);
    opensearchid.grantRead(lambdaFn);
    opensearchpassword.grantRead(os_lambdaFn);
    opensearchid.grantRead(os_lambdaFn);
    
    // API Gateway 생성
    const api = new apigateway.RestApi(this, 'ChatbotApi', {
      restApiName: 'Chatbot Service',
      description: 'This service serves as a chatbot API.',
    });

    // Lambda 통합 생성
    const chatbotIntegration = new apigateway.LambdaIntegration(chatbotFunction);
    const resetindexIntegration = new apigateway.LambdaIntegration(os_lambdaFn);

    // API Gateway에 리소스와 메서드 추가
    const chatResource = api.root.addResource('chat');
    chatResource.addMethod('POST', chatbotIntegration);
    const resetindexResource = api.root.addResource('resetindex');
    resetindexResource.addMethod('GET', resetindexIntegration);

    const ssmapi = new ssm.StringParameter(this, 'WWAPI-ApiGatewayUrlParameter', {
      parameterName: '/wwapi/api-gateway-url',
      stringValue: api.url,
    });
    // Output the SSM Parameter name
    new cdk.CfnOutput(this, 'ApiGatewayUrlParameterName', {
      value: ssmapi.parameterName,
      exportName: 'ApiGatewayUrlParameterName',
    });
    
    // API URL 출력
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: api.url,
      description: 'API Gateway URL',
    });
    // s3 출력
    new cdk.CfnOutput(this, 'S3 Bucket', {
      value: bucket.bucketName,
      description: 'S3 bucket',
    }); 

  // index APU URL 출력
    new cdk.CfnOutput(this, 'ResetIndexApiUrl', {
      value: api.url + "resetindex",
      description: 'API Gateway URL',
    });  

    // Lambda 함수의 ARN 출력
    new cdk.CfnOutput(this, 'LambdaFunctionArn', {
      value: lambdaFn.functionArn,
      description: 'Lambda Function ARN',
    });

    // OpenSearch 도메인 엔드포인트 출력
    new cdk.CfnOutput(this, 'OpenSearchDomainEndpoint', {
      value: domain.domainEndpoint,
      description: 'OpenSearch Domain Endpoint',
    });
  }
}
