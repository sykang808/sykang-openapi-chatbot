import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { Construct } from 'constructs';

export class WwapiFrontendStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    
    const apiGatewayUrlParameterName = '/wwapi/api-gateway-url';
    
    // VPC 생성
    const vpc = new ec2.Vpc(this, 'StreamlitVpc', {
      maxAzs: 2, // 가용 영역 수
    });

    // ECS 클러스터 생성
    const cluster = new ecs.Cluster(this, 'StreamlitCluster', {
      vpc: vpc,
    });
    // Docker 이미지 빌드 (build_args 전달)
    const dockerImage = new ecr_assets.DockerImageAsset(this, 'StreamlitDockerImage', {
      directory: './frontend', // Dockerfile 위치
    });
    // Define Fargate task role with permissions
    const taskRole = new iam.Role(this, 'FargateTaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });

    // Grant read access to the SSM parameter
    const parameter = ssm.StringParameter.fromStringParameterName(this, 'ImportedApiGatewayUrlParameter', apiGatewayUrlParameterName);
    parameter.grantRead(taskRole);

    // Fargate 서비스 생성
    const fargateService = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this,
      'FargateService',
      {
        cluster,
        cpu: 256,
        memoryLimitMiB: 512,
        desiredCount: 1,
        taskImageOptions: {
          image: ecs.ContainerImage.fromDockerImageAsset(dockerImage),
          containerPort: 8501,
          taskRole
        },
        publicLoadBalancer: true,
        platformVersion: ecs.FargatePlatformVersion.LATEST, // Ensure latest platform version is used
        runtimePlatform: {
          operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
          cpuArchitecture: ecs.CpuArchitecture.ARM64, // Specify ARM64 architecture
        }
      }
    );
 
    new cdk.CfnOutput(this, 'FargateAppUrl', {
      value: fargateService.loadBalancer.loadBalancerDnsName,
      description: 'The URL of the Fargate application',
    });
  }
}
