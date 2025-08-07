# API Services

Python 기반 마이크로서비스 모음

## 📋 개요

이 디렉토리는 마이크로서비스 아키텍처를 구성하는 Python 기반 백엔드 서비스들을 포함합니다. 각 서비스는 독립적으로 개발, 배포, 확장이 가능하며 특정 비즈니스 도메인을 담당합니다.

## 🏗 아키텍처

```
api/
├── exchange-api/         # 환율 정보 서비스 (포트 3009)
├── employee-api-int/     # 직원 관리 서비스 (포트 3003)  
├── pm2-manager-api/      # PM2 프로세스 관리 서비스 (포트 3006)
├── postgrest/            # PostgREST 데이터베이스 API (포트 3010)
├── shared/               # 공통 라이브러리
└── README.md            # 이 파일
```

## 🛠 기술 스택

- **Language**: Python 3.9+
- **Web Framework**: Flask
- **CORS**: Flask-CORS
- **HTTP Client**: requests
- **Database**: PostgreSQL (PostgREST 통해 접근)
- **Process Manager**: PM2
- **Deployment**: PM2 Ecosystem

## 🚀 서비스 상세

### 1. Exchange API (환율 서비스)
**위치**: `exchange-api/`  
**포트**: 3009  
**주요 기능**:
- 한국수출입은행 환율 API 연동
- 실시간 환율 정보 수집 및 저장
- 웹/챗봇용 환율 데이터 제공
- PostgREST를 통한 데이터베이스 연동

**엔드포인트**:
```
GET /health                           # 서비스 상태 확인
GET /exchange_api2db                  # 환율 데이터 수집 및 저장
GET /exchange_db2api?days=7&format=web # 환율 정보 조회 (웹용)
GET /exchange_db2api?days=2&format=chat # 환율 정보 조회 (챗봇용)
GET /api/endpoints                    # API 엔드포인트 목록
GET /                                 # 서비스 정보
```

**지원 통화**: USD, EUR, JPY100, CNH

### 2. Employee API (직원 관리 서비스)
**위치**: `employee-api-int/`  
**포트**: 3003  
**주요 기능**:
- 직원 정보 관리
- 부서별 직원 조회
- 연락처 정보 제공
- 조직도 데이터 관리

**엔드포인트**:
```
GET /api/health                       # 서비스 상태 확인
GET /api/contacts                     # 전체 직원 목록
GET /api/contacts/departments         # 부서 목록
GET /api/contacts/stats              # 직원 통계 정보
```

### 3. PM2 Manager API (프로세스 관리 서비스)
**위치**: `pm2-manager-api/`  
**포트**: 3006  
**주요 기능**:
- PM2 프로세스 상태 모니터링
- 서비스 시작/중지/재시작
- 환경 설정 관리
- 리소스 사용량 조회

**엔드포인트**:
```
GET /api/pm2/health                   # 서비스 상태 확인
GET /api/pm2/status                   # PM2 프로세스 상태
POST /api/pm2/restart                 # 프로세스 재시작
GET /api/env/services                 # 환경 설정 조회
```

### 4. PostgREST (데이터베이스 API)
**위치**: `postgrest/`  
**포트**: 3010  
**주요 기능**:
- PostgreSQL REST API 인터페이스
- 자동 API 생성 (테이블 기반)
- OpenAPI 스펙 제공
- 실시간 데이터베이스 접근

**엔드포인트**:
```
GET /                                 # OpenAPI 스펙
GET /[table_name]                     # 테이블 조회
POST /[table_name]                    # 데이터 삽입
PATCH /[table_name]                   # 데이터 수정  
DELETE /[table_name]                  # 데이터 삭제
```

**설정 파일**: `postgrest.conf`

### 5. Shared Libraries
**위치**: `shared/`  
**주요 기능**:
- 공통 유틸리티 함수
- 환율 처리 공통 로직
- 데이터베이스 연결 헬퍼

## 🚀 시작하기

### 사전 요구사항

- Python 3.9+
- pip
- PostgreSQL
- PM2

### 전체 서비스 실행

1. **PM2를 통한 통합 실행** (권장)
   ```bash
   # 프로젝트 루트에서
   pm2 start ecosystem.config.js
   ```

2. **개별 서비스 실행**
   ```bash
   # Exchange API
   cd api/exchange-api
   python exchange_service_v2.py
   
   # Employee API  
   cd api/employee-api-int
   source venv/bin/activate
   python contact_service.py
   
   # PM2 Manager API
   cd api/pm2-manager-api
   source venv/bin/activate  
   python pm2_manager_service.py
   
   # PostgREST
   cd api/postgrest
   ./postgrest postgrest.conf
   ```

### 개별 서비스 설정

#### Exchange API
```bash
cd api/exchange-api
pip install -r requirements.txt
python exchange_service_v2.py
```

#### Employee API
```bash
cd api/employee-api-int
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python contact_service.py
```

#### PM2 Manager API
```bash
cd api/pm2-manager-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python pm2_manager_service.py
```

#### PostgREST
```bash
cd api/postgrest
# PostgREST 바이너리가 이미 포함되어 있음
./postgrest postgrest.conf
```

## 🌐 접근 방법

### 직접 접근
- **Exchange API**: http://localhost:3009
- **Employee API**: http://localhost:3003  
- **PM2 Manager API**: http://localhost:3006
- **PostgREST API**: http://localhost:3010

### Nginx 프록시를 통한 접근 (권장)
- **Exchange API**: http://localhost/api/exchange/
- **Employee API**: http://localhost:3003 (직접 접근)
- **PostgREST API**: http://localhost/postgrest/

### 외부 접근
- **IP**: http://10.252.92.75/api/exchange/
- **도메인**: http://aipc.sec.samsung.net/api/exchange/

## 🔧 환경 설정

### 환경 변수
모든 환경 변수는 루트의 `env.js`에서 중앙 관리됩니다:

```javascript
// 서비스 포트 설정
services: {
  exchangeApi: { host: '0.0.0.0', port: '3009' },
  employeeApi: { host: '127.0.0.1', port: '3003' },
  pm2ManagerApi: { host: '127.0.0.1', port: '3006' },
  postgrestApi: { host: '127.0.0.1', port: '3010' }
}
```

### PM2 생태계 설정
`ecosystem.config.js`에서 모든 서비스 설정 관리:

```javascript
apps: [
  {
    name: 'exchange-api',
    script: 'exchange_service_v2.py',
    interpreter: 'python3',
    cwd: './api/exchange-api'
  },
  // ... 기타 서비스
]
```

## 📡 서비스 간 통신

### API 게이트웨이 패턴
Nginx가 리버스 프록시 역할을 수행하여 모든 API 요청을 적절한 마이크로서비스로 라우팅합니다.

```nginx
# nginx.conf
location ~ ^/api/exchange(.*)$ {
    proxy_pass http://exchange_api$1$is_args$args;
}

location /postgrest/ {
    proxy_pass http://postgrest_api/;
}
```

### 데이터베이스 접근
- **PostgREST**: 모든 서비스가 PostgREST API를 통해 데이터베이스에 접근
- **직접 연결**: 필요시 PostgreSQL에 직접 연결 가능

## 🔐 보안

### CORS 설정
```python
# Flask 서비스에서 CORS는 nginx에서 처리
# 중복 헤더 방지를 위해 Flask CORS 비활성화
```

### 환경별 보안
- **개발**: localhost 및 개발 IP 허용
- **프로덕션**: 특정 도메인만 허용
- **내부 서비스**: 127.0.0.1로 제한

## 🧪 테스트

### API 테스트
```bash
# Exchange API 상태 확인
curl http://localhost:3009/health

# 환율 정보 조회
curl "http://localhost:3009/exchange_db2api?days=7&format=web"

# Employee API 테스트
curl http://localhost:3003/api/contacts

# PostgREST API 테스트
curl http://localhost:3010/
```

### Admin 대시보드 통한 테스트
관리자 대시보드의 API Documentation 탭에서 모든 API를 실시간으로 테스트할 수 있습니다.

## 📈 모니터링

### PM2 모니터링
```bash
# 프로세스 상태 확인
pm2 status

# 로그 확인
pm2 logs exchange-api
pm2 logs employee-api
pm2 logs pm2-manager-api

# 리소스 모니터링
pm2 monit
```

### 서비스 상태 확인
```bash
# 모든 서비스 헬스 체크
curl http://localhost:3009/health
curl http://localhost:3003/api/health  
curl http://localhost:3006/api/pm2/health
curl http://localhost:3010/
```

## 🚀 배포

### PM2를 통한 배포
```bash
# 모든 서비스 시작
pm2 start ecosystem.config.js

# 특정 서비스 재시작
pm2 restart exchange-api
pm2 restart employee-api

# 환경 변수 업데이트 후 재시작
pm2 restart all --update-env
```

### 개별 서비스 배포
```bash
# Exchange API 재배포
cd api/exchange-api
pm2 restart exchange-api

# Employee API 재배포  
cd api/employee-api-int
source venv/bin/activate
pm2 restart employee-api
```

## 📋 개발 가이드라인

### 새 서비스 추가
1. `api/` 하위에 서비스 디렉토리 생성
2. `requirements.txt` 파일 생성
3. Flask 애플리케이션 구현
4. `ecosystem.config.js`에 서비스 추가
5. nginx 설정에 라우팅 규칙 추가

### 코딩 컨벤션
- Python PEP 8 스타일 가이드 준수
- Flask 애플리케이션 구조 표준화
- 에러 핸들링 및 로깅 표준화
- API 응답 형식 통일

### API 설계 원칙
- RESTful API 설계
- 명확한 엔드포인트 네이밍
- 일관된 응답 형식
- 적절한 HTTP 상태 코드 사용

## 🔍 트러블슈팅

### 일반적인 문제

1. **포트 충돌**
   ```bash
   # 포트 사용 중인 프로세스 확인
   lsof -i :3009
   
   # PM2 프로세스 정리
   pm2 delete all
   pm2 start ecosystem.config.js
   ```

2. **가상환경 문제**
   ```bash
   # 가상환경 재생성
   cd api/employee-api-int
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **PostgREST 연결 오류**
   ```bash
   # PostgreSQL 서비스 상태 확인
   brew services list | grep postgres
   
   # PostgREST 설정 확인
   cat api/postgrest/postgrest.conf
   ```

### 로그 분석
```bash
# PM2 통합 로그
pm2 logs

# 특정 서비스 로그
pm2 logs exchange-api --lines 100

# 실시간 로그 모니터링
pm2 logs --follow
```

## 🤝 기여하기

1. 새로운 마이크로서비스 개발
2. 기존 서비스 기능 확장
3. API 문서화 개선
4. 성능 최적화
5. 보안 강화

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

---

**참고**: 각 서비스는 독립적으로 개발 및 배포 가능하며, 서비스 간 의존성을 최소화하도록 설계되었습니다.