"""
Exchange Rate API Module v2
PostgREST API를 활용한 환율 서비스

한국수출입은행 환율 API 연동 및 데이터 관리 모듈입니다.
PostgREST API를 통해 PostgreSQL에 저장하고, 요청한 형식으로 환율 데이터를 제공합니다.

주요 기능:
1. 환율 API → DB 저장 (api2db) - 3단계 진행상황 표시
   GET /exchange_api2db
   
2. DB → API 데이터 제공 (db2api) - 영업일 기준 환율 조회
   GET /exchange_db2api?days=7&format=web
   GET /exchange_db2api?days=14&format=chat
   
3. 헬스체크
   GET /health
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import urllib3
import os
import sys
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from flask import Response

# 환경설정 로드 및 SSL 경고 무시 (개발환경용)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# DB 기반 환경 설정

def load_config_from_db():
    """DB에서 exchange-api 설정을 로드 (실패 시 앱 중단)"""
    try:
        # PostgREST를 통해 설정 조회
        response = requests.get('http://localhost:3010/env_configs?section=eq.services&subsection=eq.exchange-api', timeout=10)
        if response.status_code == 200:
            service_configs = response.json()
            if not service_configs:
                raise Exception("DB에 exchange-api 서비스 설정이 없습니다")
                
            service_config = {}
            for item in service_configs:
                service_config[item['key']] = item['value']
            
            # 필수 서비스 설정 확인
            required_service_keys = ['host', 'port', 'protocol']
            for key in required_service_keys:
                if key not in service_config:
                    raise Exception(f"필수 서비스 설정 '{key}'가 DB에 없습니다")
            
            # exchange 관련 설정들 조회
            exchange_sections = ['api', 'database', 'scheduler']
            exchange_config = {}
            
            for section in exchange_sections:
                response = requests.get(f'http://localhost:3010/env_configs?section=eq.exchange&subsection=eq.{section}', timeout=10)
                if response.status_code == 200:
                    section_configs = response.json()
                    exchange_config[section] = {}
                    for item in section_configs:
                        # 케밥케이스를 camelCase로 변환
                        key = item['key'].replace('-', '_')
                        if key == 'enabled':
                            exchange_config[section][key] = item['value'].lower() == 'true'
                        elif key in ['daily_update_hour', 'daily_update_minute']:
                            exchange_config[section][key] = int(item['value'])
                        else:
                            exchange_config[section][key] = item['value']
            
            # PostgREST API 설정 (기본값 사용)
            response = requests.get('http://localhost:3010/env_configs?section=eq.services&subsection=eq.postgrest-api', timeout=10)
            postgrest_config = {'host': '127.0.0.1', 'port': '3010'}  # 기본값
            if response.status_code == 200:
                postgrest_data = response.json()
                for item in postgrest_data:
                    if item['key'] in ['host', 'port']:
                        postgrest_config[item['key']] = item['value']
            
            config = {
                'services': {
                    'exchange-api': service_config,
                    'postgrest-api': postgrest_config
                },
                'exchange': exchange_config
            }
            
            print("✅ DB에서 exchange-api 설정 로드 완료")
            return config
        else:
            raise Exception(f"PostgREST API 호출 실패: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ DB 설정 로드 실패: {e}")
        print("❌ 앱을 시작할 수 없습니다. DB 설정을 확인해주세요.")
        exit(1)

# DB에서 설정 로드 (실패 시 앱 중단)
config = load_config_from_db()

app = Flask(__name__)

# CORS 설정 - 모든 도메인 허용
CORS(app)

# 스케줄러 초기화
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

# 설정값 로드
POSTGREST_BASE_URL = f"http://{config['services']['postgrest-api']['host']}:{config['services']['postgrest-api']['port']}"
EXCHANGE_RATES_TABLE = config['exchange']['database']['table_name']
EXCHANGE_API_BASE_URL = config['exchange']['api']['base_url']
EXCHANGE_API_AUTH_KEY = config['exchange']['api']['auth_key']

# 지원 통화 목록 (한국수출입은행 API 기준)
CURRENCIES = ['USD', 'EUR', 'JPY100', 'CNH']

# 시간대 헬퍼 (한국 기준 시간)
def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul"))

def today_kst():
    return now_kst().date()

def get_business_days(days):
    """영업일 계산 함수 (주말 제외)"""
    result = []
    # 한국(서울) 시간 기준으로 날짜 계산
    current = now_kst()
    count = 0
    while count < days:
        if current.weekday() < 5:  # 월-금
            result.append(current.date())
            count += 1
        current -= timedelta(days=1)
    return result

def postgrest_request(method, endpoint, data=None, params=None):
    """PostgREST API 요청 헬퍼 함수"""
    url = f"{POSTGREST_BASE_URL}/{endpoint}"
    headers = {
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method.upper() == 'PATCH':
            response = requests.patch(url, headers=headers, json=data, params=params, timeout=30)
        elif method.upper() == 'DELETE':
            response = requests.delete(url, headers=headers, params=params, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
            
        response.raise_for_status()
        
        if response.status_code == 204:  # No Content
            return {"success": True, "data": []}
        
        return {"success": True, "data": response.json() if response.text else []}
        
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}

# =================================================================
# ===== 3번 항목 수정: api2db 로직 분리 및 스케줄러 직접 호출 =====
# =================================================================

def sync_exchange_data_from_api():
    """
    [수정됨] 환율 데이터 동기화 핵심 로직.
    Flask의 HTTP 컨텍스트와 독립적으로 실행되며, 결과는 dict 형태로 반환됩니다.
    """
    steps = []
    
    try:
        # Step 1: API 설정 확인
        steps.append({"step": 1, "name": "API 설정 확인", "status": "진행중"})
        
        missing_vars = []
        if not EXCHANGE_API_BASE_URL or EXCHANGE_API_BASE_URL == "your_api_key_here":
            missing_vars.append('EXCHANGE_API_BASE_URL')
        if not EXCHANGE_API_AUTH_KEY or EXCHANGE_API_AUTH_KEY == "your_api_key_here":
            missing_vars.append('EXCHANGE_API_AUTH_KEY')
            
        if missing_vars:
            error_msg = f"API 환경변수 누락: {', '.join(missing_vars)}"
            steps[-1].update({"status": "실패", "error": error_msg})
            return {"success": False, "steps": steps, "error": error_msg}
            
        health_check = postgrest_request('GET', EXCHANGE_RATES_TABLE, params={'limit': 1})
        if not health_check['success']:
            error_msg = f"PostgREST 연결 실패: {health_check['error']}"
            steps[-1].update({"status": "실패", "error": error_msg})
            return {"success": False, "steps": steps, "error": error_msg}
            
        steps[-1].update({"status": "완료", "details": "API 환경변수 및 PostgREST 연결 확인됨"})

        # Step 2: 최신 날짜 및 업데이트 범위 확인
        steps.append({"step": 2, "name": "최신 날짜 및 업데이트 범위 확인", "status": "진행중"})
        
        latest_data = postgrest_request('GET', EXCHANGE_RATES_TABLE, params={'select': 'date', 'order': 'date.desc', 'limit': 1})
        
        # 한국(서울) 기준 오늘 날짜
        today = today_kst()
        if latest_data['success'] and latest_data['data']:
            latest_date_str = latest_data['data'][0]['date']
            latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
        else:
            latest_date = today - timedelta(days=100)
        
        if latest_date >= today:
            details = f"최신 데이터 존재 ({latest_date.strftime('%Y-%m-%d')}), 업데이트 불필요"
            steps[-1].update({"status": "완료", "details": details})
            return {"success": True, "steps": steps, "summary": "업데이트할 새로운 데이터가 없습니다"}

        business_days = []
        current = latest_date + timedelta(days=1)
        while current <= today:
            if current.weekday() < 5:
                business_days.append(current)
            current += timedelta(days=1)
        
        if not business_days:
            details = f"최신 날짜: {latest_date.strftime('%Y-%m-%d')}, 업데이트할 영업일이 없습니다"
            steps[-1].update({"status": "완료", "details": details})
            return {"success": True, "steps": steps, "summary": "업데이트할 새로운 데이터가 없습니다"}
            
        steps[-1].update({"status": "완료", "details": f"최신 날짜: {latest_date.strftime('%Y-%m-%d')}, 업데이트 필요 영업일: {len(business_days)}일"})

        # Step 3: API 호출 및 데이터 저장
        steps.append({"step": 3, "name": "API 호출 및 데이터 저장", "status": "진행중"})
        
        # --- 1번 항목 수정: N+1 문제 해결을 위한 일괄 처리 시작 ---
        # 업데이트 필요한 날짜들에 대해 DB에 이미 데이터가 있는지 한번에 확인
        date_strs = [d.strftime('%Y-%m-%d') for d in business_days]
        existing_data_result = postgrest_request('GET', EXCHANGE_RATES_TABLE, params={'date': f'in.({",".join(date_strs)})'})
        existing_dates = set()
        if existing_data_result['success']:
            existing_dates = {item['date'] for item in existing_data_result['data']}
        # --- 1번 항목 수정 끝 ---

        success_count = 0
        failed_dates = []
        to_insert = []
        to_update = []
        
        for date in business_days:
            params = {'authkey': EXCHANGE_API_AUTH_KEY, 'searchdate': date.strftime("%Y%m%d"), 'data': 'AP01'}
            try:
                response = requests.get(EXCHANGE_API_BASE_URL, params=params, verify=False, timeout=30)
                response.raise_for_status()
                api_data = response.json()

                if not api_data: # 휴일 등 데이터가 없는 경우
                    continue

                rates_dict = {cur: None for cur in CURRENCIES}
                for item in api_data:
                    cur_unit = item.get('cur_unit', '').strip()
                    deal_bas_r = item.get('deal_bas_r', '0')
                    try:
                        rate_value = float(deal_bas_r.replace(',', ''))
                        if cur_unit == 'JPY(100)':
                            rates_dict['JPY100'] = rate_value
                        elif cur_unit in rates_dict:
                            rates_dict[cur_unit] = rate_value
                    except:
                        continue
                
                data_to_save = {
                    'date': date.strftime('%Y-%m-%d'),
                    'usd': rates_dict['USD'],
                    'eur': rates_dict['EUR'],
                    'jpy100': rates_dict['JPY100'],
                    'cnh': rates_dict['CNH']
                }

                # --- 1번 항목 수정: 삽입/업데이트 목록 분리 ---
                if data_to_save['date'] in existing_dates:
                    to_update.append(data_to_save)
                else:
                    to_insert.append(data_to_save)
                # --- 1번 항목 수정 끝 ---

            except Exception as e:
                failed_dates.append(date.strftime("%Y-%m-%d"))
                continue

        # --- 1번 항목 수정: 일괄 삽입 및 개별 업데이트 실행 ---
        if to_insert:
            insert_result = postgrest_request('POST', EXCHANGE_RATES_TABLE, data=to_insert)
            if insert_result['success']:
                success_count += len(insert_result['data'])
            else:
                # bulk insert 실패 시 개별 날짜를 실패로 기록
                failed_dates.extend([d['date'] for d in to_insert])

        for item in to_update:
            update_result = postgrest_request('PATCH', EXCHANGE_RATES_TABLE, 
                                            data=item,
                                            params={'date': f"eq.{item['date']}"})
            if update_result['success']:
                success_count += 1
            else:
                failed_dates.append(item['date'])
        # --- 1번 항목 수정 끝 ---

        steps[-1].update({"status": "완료", "details": f"성공: {success_count}일, 실패: {len(failed_dates)}일"})

        return {
            "success": True,
            "steps": steps,
            "summary": f"총 {len(business_days)}일 중 {success_count}일 업데이트 완료",
            "failed_dates": failed_dates if failed_dates else None
        }

    except Exception as e:
        error_msg = str(e)
        if steps:
            steps[-1].update({"status": "실패", "error": error_msg})
        return {"success": False, "steps": steps, "error": error_msg}


def run_scheduled_api2db():
    """[수정됨] 스케줄러에서 실행할 함수. Flask 컨텍스트 없이 핵심 로직을 직접 호출합니다."""
    try:
        print(f"[{now_kst()}] 스케줄된 환율 API 업데이트 시작...")
        
        # Flask 컨텍스트 없이 핵심 로직 함수를 직접 호출
        result = sync_exchange_data_from_api()
        
        if result.get('success'):
            print(f"[{now_kst()}] 스케줄된 환율 API 업데이트 성공: {result.get('summary', '')}")
        else:
            print(f"[{now_kst()}] 스케줄된 환율 API 업데이트 실패: {result.get('error', '')}")
    
    except Exception as e:
        print(f"[{now_kst()}] 스케줄된 환율 API 업데이트 오류: {str(e)}")

@app.route('/api/exchange_api2db', methods=['GET'])
def api2db():
    """
    [수정됨] 한국수출입은행 환율 API → 데이터베이스 저장 기능.
    핵심 로직을 호출하고 결과를 JSON으로 변환하여 반환하는 '창구' 역할만 수행합니다.
    """
    result = sync_exchange_data_from_api()
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code

# =================================================================
# ===== 1번 항목 수정: db2api 성능 최적화 ==========================
# =================================================================

@app.route('/api/exchange_db2api', methods=['GET'])
def db2api():
    """
    [수정됨] 데이터베이스 → API 환율 데이터 제공 기능.
    루프 내 DB 조회를 제거하고 일괄 조회 방식으로 변경하여 성능을 개선합니다.
    """
    try:
        days_param = request.args.get('days')
        format_type = request.args.get('format')
        
        if not format_type:
            return jsonify({"error": "format 파라미터가 필요합니다"}), 400
            
        format_type = format_type.lower()
        if format_type not in ['web', 'chat']:
            return jsonify({"error": "format은 'web' 또는 'chat'이어야 합니다"}), 400
        
        # format별 기본값 설정
        if format_type == 'chat':
            days = int(days_param) if days_param else 2  # chat 기본값: 2일
        elif format_type == 'web':
            days = int(days_param) if days_param else 14  # web 기본값: 14일
        
        if days < 1 or days > 100:
            return jsonify({"error": "days는 1-100 사이여야 합니다"}), 400

        business_days = get_business_days(days)
        if not business_days:
            return jsonify({"error": "조회할 영업일 데이터가 없습니다"}), 404
        
        # --- 1번 항목 수정: N+1 문제 해결 (web, chat 공통) ---
        # 필요한 모든 날짜를 문자열 리스트로 변환
        date_strs_to_fetch = [d.strftime('%Y-%m-%d') for d in business_days]
        
        # 단 한 번의 요청으로 모든 날짜의 데이터를 가져옴
        print(f"🔍 요청된 날짜들: {date_strs_to_fetch}")
        all_data_result = postgrest_request(
            'GET', EXCHANGE_RATES_TABLE, 
            params={
                'date': f'in.({",".join(date_strs_to_fetch)})',
                'order': 'date.desc' # 최신순으로 정렬
            }
        )
        
        print(f"📊 조회된 데이터 개수: {len(all_data_result.get('data', []))}")
        if all_data_result.get('data'):
            available_dates = [item['date'] for item in all_data_result['data']]
            print(f"📅 조회된 날짜들: {available_dates}")

        # 3단계: 가장 최근 영업일 데이터 확인 (chat/web 공통)
        latest_date_str = business_days[0].strftime('%Y-%m-%d')
        latest_data_exists = False
        
        if all_data_result['success'] and all_data_result['data']:
            available_dates = [item['date'] for item in all_data_result['data']]
            latest_data_exists = latest_date_str in available_dates
            print(f"✅ 최신 영업일({latest_date_str}) 데이터 존재: {latest_data_exists}")
        
        # 3-1단계: 최신 데이터가 없으면 api2db 실행
        if not latest_data_exists:
            print(f"❌ 최신 영업일({latest_date_str}) 데이터 없음. api2db 자동 실행 중...")
            
            api2db_result = sync_exchange_data_from_api()
            if api2db_result['success']:
                print("✅ api2db 실행 완료. 데이터 다시 조회 중...")
                
                # 데이터 다시 조회 (재귀 호출 대신 직접 조회)
                all_data_result = postgrest_request(
                    'GET', EXCHANGE_RATES_TABLE, 
                    params={
                        'date': f'in.({",".join(date_strs_to_fetch)})',
                        'order': 'date.desc'
                    }
                )
                print(f"🔄 재조회 결과: {len(all_data_result.get('data', []))}개")
            else:
                print(f"❌ api2db 실행 실패: {api2db_result.get('error', '알 수 없는 오류')}")
                return jsonify({"error": f"api2db 실행 실패: {api2db_result.get('error', '알 수 없는 오류')}"}), 500
        
        # 최종 데이터 확인
        if not all_data_result['success'] or not all_data_result['data']:
            return jsonify({"error": "요청된 기간의 환율 데이터가 없습니다"}), 404
        
        db_data = all_data_result['data']
        # --- 1번 항목 수정 끝 ---

        if format_type == 'web':
            # [수정됨] 이미 가져온 데이터(db_data)를 가공하기만 함
            web_data = []
            for row in db_data:
                web_data.append({
                    'date': row['date'],
                    'USD': float(row.get('usd') or 0.0),
                    'EUR': float(row.get('eur') or 0.0),
                    'JPY100': float(row.get('jpy100') or 0.0),
                    'CNH': float(row.get('cnh') or 0.0)
                })

            return jsonify({
                'success': True,
                'data': web_data,
                'metadata': {
                    'total_days': len(web_data),
                    'requested_days': days,
                    'latest_date': web_data[0]['date'],
                    'available_currencies': CURRENCIES,
                    'format': 'web',
                    'description': 'All rates are based on KRW. JPY100 means 100 yen.'
                }
            })
        
        elif format_type == 'chat':
            # [수정됨] 이미 가져온 데이터(db_data)에서 최신 2일치 데이터를 사용
            if len(db_data) < 2:
                return jsonify({"error": "변화율 계산을 위해 최소 2일의 데이터가 필요합니다"}), 404
                
            today_data = db_data[0]
            yesterday_data = db_data[1]
            formatted_rates = {}
            
            for currency in CURRENCIES:
                key = currency.lower() # DB 컬럼명은 소문자
                today_rate = today_data.get(key)
                yest_rate = yesterday_data.get(key)

                if today_rate is not None and yest_rate is not None and yest_rate != 0:
                    change_rate = ((today_rate - yest_rate) / yest_rate) * 100
                    formatted_rates[currency] = round(today_rate, 2)
                    formatted_rates[f"{currency}_trend"] = round(change_rate, 2)
                else:
                    formatted_rates[currency] = round(today_rate, 2) if today_rate is not None else 0
                    formatted_rates[f"{currency}_trend"] = 0.0

            return jsonify({
                'success': True,
                'data': [formatted_rates],
                'metadata': {
                    'comparison_dates': {
                        'today': today_data['date'],
                        'yesterday': yesterday_data['date']
                    },
                    'requested_days': days,
                    'format': 'chat',
                    'description': 'Rate comparison with trend analysis for chatbot'
                }
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """헬스체크"""
    try:
        # PostgREST 연결 테스트
        health_test = postgrest_request('GET', EXCHANGE_RATES_TABLE, params={'limit': 1})
        
        if not health_test['success']:
            return jsonify({
                'status': 'unhealthy',
                'postgrest': 'disconnected',
                'error': health_test['error'],
                'timestamp': datetime.now().isoformat()
            }), 500
        
        # 최신 데이터 확인
        stats_result = postgrest_request('GET', EXCHANGE_RATES_TABLE, 
                                       params={'select': 'date', 'order': 'date.desc', 'limit': 1})
        
        if stats_result['success'] and stats_result['data']:
            latest_date = stats_result['data'][0]['date']
        else:
            latest_date = 'no data'
            
        # 전체 레코드 수 확인
        # PostgREST는 count를 위해 별도의 헤더를 사용하거나 RPC를 구성해야 하므로, 여기서는 간단히 GET으로 대체
        count_result = postgrest_request('GET', EXCHANGE_RATES_TABLE, params={'select': 'date'})
        total_records = len(count_result['data']) if count_result['success'] else 0
        
        return jsonify({
            'status': 'healthy',
            'postgrest': 'connected',
            'postgrest_url': POSTGREST_BASE_URL,
            'table': EXCHANGE_RATES_TABLE,
            'data_info': {
                'latest_data': latest_date,
                'total_records': total_records
            },
            'supported_currencies': CURRENCIES,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'postgrest': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# OpenAPI 명세 파일 제공 라우트
@app.route('/openapi.yaml', methods=['GET'])
def serve_openapi_yaml():
    """OpenAPI 명세 파일 제공"""
    file_path = os.path.join(os.path.dirname(__file__), 'openapi.yaml')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()
        return Response(yaml_content, mimetype='text/yaml')
    except Exception as e:
        return jsonify({"error": f"OpenAPI 명세 파일을 읽을 수 없습니다: {str(e)}"}), 500



if __name__ == '__main__':
    port = int(config['services']['exchange-api']['port'])
    host = config['services']['exchange-api']['host']
    
    # 스케줄러 작업 등록 - DB에서 시간 설정 로드
    try:
        if config['exchange']['scheduler']['enabled']:
            scheduler.add_job(
                func=run_scheduled_api2db, # 수정된 스케줄러 함수를 등록
                trigger=CronTrigger(
                    hour=config['exchange']['scheduler']['daily_update_hour'],
                    minute=config['exchange']['scheduler']['daily_update_minute'],
                    timezone=ZoneInfo("Asia/Seoul")
                ),
                id='daily_exchange_update',
                name='Daily Exchange Rate Update',
                replace_existing=True
            )
            print(f"⏰ Scheduler: Daily exchange rate update at {config['exchange']['scheduler']['daily_update_hour']:02d}:{config['exchange']['scheduler']['daily_update_minute']:02d}")
        else:
            print(f"⏰ Scheduler: Disabled")
    except Exception as e:
        print(f"❌ Scheduler registration failed: {e}")
        scheduler.shutdown()
        print(f"⏰ Scheduler: Disabled due to configuration error")
    
    # 앱 종료 시 스케줄러도 종료
    atexit.register(lambda: scheduler.shutdown())
    
    print(f"🔄 Exchange API v2 starting on {host}:{port}")
    print(f"📊 PostgREST API: {POSTGREST_BASE_URL}")
    print(f"📋 Table: {EXCHANGE_RATES_TABLE}")
    print(f"💱 Supported currencies: {', '.join(CURRENCIES)}")
    print(f"🔗 External API: {EXCHANGE_API_BASE_URL}")
    
    app.run(debug=False, host=host, port=port)
