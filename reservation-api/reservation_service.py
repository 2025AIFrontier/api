import os
from datetime import datetime
from zoneinfo import ZoneInfo  # MODERNIZED: pytz 대신 표준 라이브러리 zoneinfo 사용

import requests
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

# --- Flask 앱 및 CORS 설정 ---
app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:3001",
    "http://localhost:3002",
    "http://10.252.92.75",
    "http://aipc.sec.samsung.net"
])

# JSON 인코딩 설정: 한글 깨짐 방지
app.config['JSON_AS_ASCII'] = False

# --- 상수 및 설정 ---
POSTGREST_BASE_URL = 'http://localhost:3010'
KST = ZoneInfo('Asia/Seoul')  # 한국시간 타임존

# --- 헬퍼 함수 (코드 중복 제거 및 일관성 유지) ---

def api_success(data=None, status_code=200, message=None, pagination=None):
    """표준 성공 응답을 생성합니다."""
    response = {
        'success': True,
        'timestamp': datetime.now(KST).isoformat()
    }
    if data is not None:
        response['data'] = data
    if message:
        response['message'] = message
    if pagination:
        response['pagination'] = pagination
    return jsonify(response), status_code

def api_error(message, status_code=500, error_details=None):
    """표준 에러 응답을 생성합니다."""
    response = {'success': False, 'message': message}
    if error_details and app.debug:
        response['error'] = str(error_details)
    print(f"❌ API Error: {message} | Status: {status_code} | Details: {error_details}")
    return jsonify(response), status_code


def load_config_from_db():
    """DB에서 reservation-api 설정을 로드합니다."""
    try:
        url = 'http://localhost:3010/env_configs?section=eq.services&subsection=eq.reservation-api'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        configs_list = response.json()
        if not configs_list:
            raise ValueError("DB에 reservation-api 설정이 없습니다.")
            
        config = {item['key']: item['value'] for item in configs_list}
        
        required_keys = ['host', 'port', 'protocol']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"필수 설정 '{key}'가 DB에 없습니다.")
        
        print("✅ DB에서 설정 로드 완료")
        return config
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"❌ DB 설정 로드 실패: {e}")
        print("❌ 앱을 시작할 수 없습니다. DB 설정을 확인해주세요.")
        exit(1)

# --- API 엔드포인트 ---

@app.route('/api/reservations', methods=['GET'])
def get_reservations():
    """(최적화) 예약 목록 조회 API - 단일 PostgREST 호출"""
    try:
        # OPTIMIZED: 입력값 검증 강화
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
            if page < 1 or limit < 1:
                raise ValueError("page와 limit 값은 1 이상이어야 합니다.")
        except ValueError as e:
            return api_error(f"잘못된 요청 파라미터입니다: {e}", 400)

        # 필터링 및 정렬 파라미터 구성
        query_params = []
        if request.args.get('type'): query_params.append(f'type=eq.{request.args.get("type")}')
        if request.args.get('target'): query_params.append(f'target=eq.{request.args.get("target")}')
        if request.args.get('email'): query_params.append(f'emailaddress=ilike.*{request.args.get("email")}*')
        if request.args.get('session'): query_params.append(f'session=eq.{request.args.get("session")}')
        if request.args.get('date_from'): query_params.append(f'time=gte.{request.args.get("date_from")}')
        if request.args.get('date_to'): query_params.append(f'time=lte.{request.args.get("date_to")}')
        
        offset = (page - 1) * limit
        query_params.append(f'limit={limit}')
        query_params.append(f'offset={offset}')
        
        sort_by = request.args.get('sort_by', 'time')
        sort_order = request.args.get('sort_order', 'desc')
        query_params.append(f'order={sort_by}.{sort_order}')
        
        # PostgREST API 호출
        url = f'{POSTGREST_BASE_URL}/reservation_table?{"&".join(query_params)}'
        
        # OPTIMIZED: count=exact 헤더로 요청을 한 번만 보내 데이터와 전체 개수를 함께 받음
        headers = {'Prefer': 'count=exact'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # 2xx 응답 코드가 아니면 HTTPError 발생

        data = response.json()
        
        # OPTIMIZED: Content-Range 헤더에서 전체 개수 파싱
        content_range = response.headers.get('Content-Range')
        total_count = int(content_range.split('/')[-1]) if content_range and '/' in content_range else len(data)

        pagination_info = {
            'total': total_count, 'page': page, 'limit': limit,
            'pages': (total_count + limit - 1) // limit,
            'has_next': offset + limit < total_count, 'has_prev': page > 1
        }
        
        return api_success(data=data, pagination=pagination_info)
            
    except requests.exceptions.HTTPError as e:
        return api_error(f'PostgREST API 오류: {e.response.status_code}', e.response.status_code, e.response.text)
    except Exception as e:
        return api_error('예약 조회 중 서버 오류가 발생했습니다.', 500, e)

@app.route('/api/reservations', methods=['POST'])
def create_reservation():
    """예약 생성 API - PostgREST 활용"""
    try:
        data = request.get_json()
        if not data:
            return api_error('요청 본문이 비어있습니다.', 400)

        required_fields = ['type', 'target', 'emailaddress', 'session', 'reason']
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            return api_error(f'필수 필드가 누락되었습니다: {", ".join(missing_fields)}', 400)
        
        # 시간 필드 처리 (타임존 포함)
        if 'time' not in data or not data['time']:
            data['time'] = datetime.now(KST).isoformat()
        else:
            try:
                # 'Z'를 포함한 ISO 8601 형식을 파싱 (Python 3.11 미만 호환성을 위해 .replace 사용)
                dt_obj = datetime.fromisoformat(data['time'].replace('Z', '+00:00'))
                
                if dt_obj.tzinfo is None: # 타임존 정보가 없는 naive datetime이면 KST로 간주
                    dt_obj = KST.localize(dt_obj)
                else: # 타임존 정보가 있으면 KST로 변환
                    dt_obj = dt_obj.astimezone(KST)
                
                data['time'] = dt_obj.isoformat()
            except ValueError as e:
                return api_error(f"잘못된 시간 형식입니다: {data['time']}", 400, e)

        response = requests.post(
            f'{POSTGREST_BASE_URL}/reservation_table', json=data,
            headers={'Prefer': 'return=representation', 'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        
        created_data = response.json()
        return api_success(
            data=created_data[0] if created_data else data, 
            status_code=201, 
            message='예약이 성공적으로 생성되었습니다.'
        )
            
    except requests.exceptions.HTTPError as e:
        return api_error(f'예약 생성 실패: {e.response.status_code}', e.response.status_code, e.response.text)
    except Exception as e:
        return api_error('예약 생성 중 서버 오류가 발생했습니다.', 500, e)

@app.route('/api/reservations/<int:reservation_id>', methods=['GET'])
def get_reservation(reservation_id):
    """특정 예약 조회 API - PostgREST 활용"""
    try:
        response = requests.get(f'{POSTGREST_BASE_URL}/reservation_table?id=eq.{reservation_id}', timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if not data:
            return api_error('해당 예약을 찾을 수 없습니다.', 404)
        
        return api_success(data=data[0])

    except requests.exceptions.HTTPError as e:
        return api_error(f'PostgREST API 오류: {e.response.status_code}', e.response.status_code, e.response.text)
    except Exception as e:
        return api_error('예약 조회 중 서버 오류가 발생했습니다.', 500, e)

@app.route('/api/reservations/<int:reservation_id>', methods=['PATCH'])  # NOTE: 부분 수정을 의미하는 PATCH로 변경
def update_reservation(reservation_id):
    """예약 수정 API - PostgREST 활용"""
    try:
        data = request.get_json()
        if not data:
            return api_error('수정할 내용이 없습니다.', 400)
            
        response = requests.patch(
            f'{POSTGREST_BASE_URL}/reservation_table?id=eq.{reservation_id}', json=data,
            headers={'Content-Type': 'application/json', 'Prefer': 'return=representation'},
            timeout=30
        )
        response.raise_for_status()
        
        updated_data = response.json()
        if not updated_data:
            return api_error('해당 예약을 찾을 수 없거나 수정된 내용이 없습니다.', 404)
            
        return api_success(data=updated_data[0], message='예약이 성공적으로 수정되었습니다.')

    except requests.exceptions.HTTPError as e:
        return api_error(f'예약 수정 실패: {e.response.status_code}', e.response.status_code, e.response.text)
    except Exception as e:
        return api_error('예약 수정 중 서버 오류가 발생했습니다.', 500, e)

@app.route('/api/reservations/<int:reservation_id>', methods=['DELETE'])
def delete_reservation(reservation_id):
    """예약 삭제 API - PostgREST 활용"""
    try:
        response = requests.delete(
            f'{POSTGREST_BASE_URL}/reservation_table?id=eq.{reservation_id}',
            headers={'Prefer': 'return=representation'}, timeout=30
        )
        response.raise_for_status()

        deleted_data = response.json()
        if not deleted_data:
            return api_error('해당 예약을 찾을 수 없습니다.', 404)
        
        return api_success(data=deleted_data[0], message='예약이 성공적으로 삭제되었습니다.')

    except requests.exceptions.HTTPError as e:
        return api_error(f'예약 삭제 실패: {e.response.status_code}', e.response.status_code, e.response.text)
    except Exception as e:
        return api_error('예약 삭제 중 서버 오류가 발생했습니다.', 500, e)

# --- 유틸리티 엔드포인트 ---

@app.route('/api/health', methods=['GET'])
def health_check():
    """서비스 상태 및 PostgREST 연결을 확인하는 헬스체크"""
    postgrest_status = 'disconnected'
    try:
        response = requests.get(f'{POSTGREST_BASE_URL}/', timeout=5)
        if response.status_code == 200:
            postgrest_status = 'connected'
    except requests.exceptions.RequestException:
        pass
    
    return jsonify({
        'status': 'healthy',
        'service': 'Reservation API',
        'version': '1.1.0-optimized', # 버전 정보 업데이트
        'timestamp': datetime.now().isoformat(),
        'dependencies': {
            'postgrest_status': postgrest_status
        }
    })

@app.route('/openapi.yaml')
def serve_openapi_spec():
    """OpenAPI 스펙 파일을 제공합니다."""
    try:
        openapi_path = os.path.join(os.path.dirname(__file__), 'openapi.yaml')
        with open(openapi_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return Response(content, mimetype='text/yaml')
    except FileNotFoundError:
        return api_error('OpenAPI 스펙 파일을 찾을 수 없습니다.', 404)
    except Exception as e:
        return api_error('OpenAPI 스펙 로드 중 오류 발생', 500, e)

# --- 애플리케이션 실행 ---

if __name__ == '__main__':
    # DB에서 설정 로드 (실패 시 앱 중단)
    config = load_config_from_db()
    
    # 환경 변수 또는 DB 설정값으로 앱 실행
    host = config['host']
    port = int(config['port'])
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    app.debug = debug
    
    print("==============================================")
    print(f"🚗 Reservation API (Optimized) starting...")
    print(f"   - Mode: {'DEBUG' if debug else 'PRODUCTION'}")
    print(f"   - Listening on: http://{host}:{port}")
    print(f"   - PostgREST endpoint: {POSTGREST_BASE_URL}")
    print("==============================================")
    
    app.run(host=host, port=port)