from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import random
import os
import requests
import json
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# JSON 인코딩 설정: 한글 문자 제대로 표시
app.config['JSON_AS_ASCII'] = False

def load_config_from_db():
    """DB에서 employee-api 설정을 로드 (실패 시 앱 중단)"""
    try:
        # PostgREST를 통해 설정 조회
        response = requests.get('http://localhost:3010/env_configs?section=eq.services&subsection=eq.employee-api', timeout=10)
        if response.status_code == 200:
            configs = response.json()
            if not configs:
                raise Exception("DB에 employee-api 설정이 없습니다")
                
            config = {}
            for item in configs:
                config[item['key']] = item['value']
            
            # 필수 설정 확인
            required_keys = ['host', 'port', 'protocol']
            for key in required_keys:
                if key not in config:
                    raise Exception(f"필수 설정 '{key}'가 DB에 없습니다")
            
            print("✅ DB에서 설정 로드 완료")
            return config
        else:
            raise Exception(f"PostgREST API 호출 실패: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ DB 설정 로드 실패: {e}")
        print("❌ 앱을 시작할 수 없습니다. DB 설정을 확인해주세요.")
        exit(1)

# 가짜 직원 데이터 생성 함수
def generate_fake_employees():
    """랜덤한 한국 직원 데이터 50명 생성"""
    departments = ['개발팀', '마케팅팀', '영업팀', '인사팀', '재무팀', '디자인팀', '기획팀', '운영팀']
    companies = ['내부전자', '내부SDS', '내부디스플레이', '내부바이오로직스', '내부물산']
    first_names = ['김', '이', '박', '최', '정', '강', '조', '윤', '장', '임']
    last_names = ['민준', '서연', '도윤', '하은', '시우', '수아', '주원', '다인', '건우', '유나', 
                 '현우', '사랑', '준서', '하율', '지후', '윤서']
    
    positions = ['팀장', '과장', '대리', '주임', '사원', '수석', '책임', '선임']
    locations = ['서울본사', '부산지사', '대구지사', '광주지사', '대전지사']
    phone_prefixes = ['010', '011', '016', '017', '018', '019']
    
    descriptions = [
        '프론트엔드 개발 전문가', '백엔드 시스템 개발자', '데이터베이스 관리 담당',
        '모바일 앱 개발자', 'UI/UX 디자인 전문가', '마케팅 전략 기획자',
        '고객 관계 관리 담당', '재무 분석 전문가', '인사 관리 담당자',
        '품질 관리 전문가', '프로젝트 매니저', '비즈니스 분석가'
    ]

    employees = []
    
    for i in range(1, 51):
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        full_name = first_name + last_name
        department = random.choice(departments)
        company = random.choice(companies)
        description = random.choice(descriptions)
        
        # 랜덤한 과거 날짜 생성
        random_days = random.randint(1, 365)
        updated_at = (datetime.now() - timedelta(days=random_days)).isoformat()
        join_date = (datetime.now() - timedelta(days=random.randint(30, 2000))).isoformat()[:10]
        
        # 전화번호 생성
        phone_number = f"{random.choice(phone_prefixes)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
        ext_number = f"{random.randint(1000, 9999)}"
        
        employee = {
            'id': i,
            'employee_number': f"EMP{i:04d}",
            'full_name': full_name,
            'email_address': f'{full_name.lower()}@internal.com',
            'phone_number': phone_number,
            'extension': ext_number,
            'company_name': company,
            'department_name': department,
            'position': random.choice(positions),
            'location': random.choice(locations),
            'description': description,
            'join_date': join_date,
            'updated_at': updated_at,
            'status': 'active',
            'avatar_url': f'/api/avatar/{i}'
        }
        
        employees.append(employee)
    
    return employees

# 가짜 데이터 생성 (서버 시작 시 한 번만 생성)
fake_employees = generate_fake_employees()

@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """직원 연락처 목록 조회 API - 웹 페이지 호출용"""
    try:
        # 쿼리 파라미터 가져오기
        fullname = request.args.get('fullname', '').strip()
        emailaddress = request.args.get('emailaddress', '').strip()
        departmentname = request.args.get('departmentname', '').strip()
        companyname = request.args.get('companyname', '').strip()
        position = request.args.get('position', '').strip()
        location = request.args.get('location', '').strip()
        
        # 페이지네이션 파라미터
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        # 정렬 파라미터
        sort_by = request.args.get('sort_by', 'full_name')
        sort_order = request.args.get('sort_order', 'asc').lower()
        
        # 필터링 적용
        filtered_employees = fake_employees.copy()
        
        if fullname:
            filtered_employees = [emp for emp in filtered_employees 
                                if fullname.lower() in emp['full_name'].lower()]
        
        if emailaddress:
            filtered_employees = [emp for emp in filtered_employees 
                                if emailaddress.lower() in emp['email_address'].lower()]
        
        if departmentname:
            filtered_employees = [emp for emp in filtered_employees 
                                if departmentname.lower() in emp['department_name'].lower()]
        
        if companyname:
            filtered_employees = [emp for emp in filtered_employees 
                                if companyname.lower() in emp['company_name'].lower()]
                                
        if position:
            filtered_employees = [emp for emp in filtered_employees 
                                if position.lower() in emp['position'].lower()]
                                
        if location:
            filtered_employees = [emp for emp in filtered_employees 
                                if location.lower() in emp['location'].lower()]
        
        # 정렬 적용
        reverse_sort = sort_order == 'desc'
        if sort_by in ['full_name', 'department_name', 'company_name', 'position', 'location']:
            filtered_employees.sort(key=lambda x: x.get(sort_by, ''), reverse=reverse_sort)
        
        # 총 개수
        total_count = len(filtered_employees)
        
        # 페이지네이션 적용
        paginated_employees = filtered_employees[offset:offset + limit]
        
        # 응답 데이터 구성
        response = {
            'success': True,
            'data': paginated_employees,
            'pagination': {
                'total': total_count,
                'page': page,
                'limit': limit,
                'offset': offset,
                'pages': (total_count + limit - 1) // limit,
                'has_next': offset + limit < total_count,
                'has_prev': page > 1
            },
            'filters': {
                'fullname': fullname,
                'emailaddress': emailaddress,
                'departmentname': departmentname,
                'companyname': companyname,
                'position': position,
                'location': location
            },
            'sort': {
                'sort_by': sort_by,
                'sort_order': sort_order
            },
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Contact API Error: {e}")
        return jsonify({
            'success': False,
            'data': [],
            'message': '서버 오류가 발생했습니다.',
            'error': str(e) if app.debug else None
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """헬스체크"""
    return jsonify({
        'status': 'healthy',
        'service': 'Contact API',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'total_contacts': len(fake_employees)
    })

@app.route('/openapi.yaml')
def serve_openapi_spec():
    try:
        openapi_path = os.path.join(os.path.dirname(__file__), 'openapi.yaml')
        with open(openapi_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return Response(content, mimetype='text/yaml')
    except Exception as e:
        return jsonify({'error': f'Failed to load OpenAPI spec: {str(e)}'}), 500


if __name__ == '__main__':
    # DB에서 설정 로드 (실패 시 앱 중단)
    config = load_config_from_db()
    
    host = config['host']
    port = int(config['port'])
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    print(f"🌐 Contact API for Web starting on {host}:{port}")
    print(f"📊 Total contacts loaded: {len(fake_employees)}")
    print(f"🔍 Simplified features: pagination, filtering, sorting")
    print(f"⚙️  Configuration loaded from database")
    
    app.run(debug=debug, host=host, port=port)