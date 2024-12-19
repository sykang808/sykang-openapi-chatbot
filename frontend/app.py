import streamlit as st
import requests
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError

def get_api_url_from_ssm(parameter_name: str, region: str = "us-west-2") -> str:
    """
    AWS SSM Parameter Store에서 API Gateway URL을 가져옵니다.
    :param parameter_name: SSM Parameter 이름
    :param region: AWS 리전 (기본값: us-west-2)
    :return: API Gateway URL 문자열
    """
    try:
        # boto3 클라이언트 생성
        ssm_client = boto3.client("ssm", region_name=region)

        # SSM Parameter 가져오기
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except (BotoCoreError, ClientError) as error:
        st.error(f"SSM Parameter를 가져오는 중 오류가 발생했습니다: {error}")
        return None

# SSM Parameter Store에서 API Gateway URL 가져오기
parameter_name = '/wwapi/api-gateway-url'  # SSM Parameter 이름
region = "us-west-2"  # AWS 리전
api_gateway_url = get_api_url_from_ssm(parameter_name, region)

if not api_gateway_url:
    st.error("API Gateway URL을 가져올 수 없습니다. 환경 변수를 확인해주세요.")
else:
    st.title("Chatbot")

    user_input = st.text_input("메시지를 입력하세요:")

    if st.button("전송"):
        if user_input:
            response = requests.post(api_gateway_url + "/chat", json={"message": user_input})
            if response.status_code == 200:
                bot_response = response.json().get('response', '응답을 받을 수 없습니다.')
                # 챗봇 응답을 더 보기 좋게 표시
                st.markdown(f"**챗봇 응답:** {bot_response}")
            else:
                st.error("오류가 발생했습니다. 다시 시도해주세요.")
        else:
            st.warning("메시지를 입력해주세요.")
