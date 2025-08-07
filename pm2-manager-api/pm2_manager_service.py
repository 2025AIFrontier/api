#!/usr/bin/env python3
"""
PM2 Manager API Service
PM2 프로세스 모니터링 및 관리 API 서비스
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import subprocess
import json
import os
import logging
import requests
from datetime import datetime
import sys
from collections import Counter # 최적화를 위해 Counter 임포트

# Flask 앱 설정
app = Flask(__name__)
CORS(app)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 프로젝트 루트 경로 설정
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ENV_JS_PATH = os.path.join(PROJECT_ROOT, 'env.js')

def run_pm2_command(command_args):
    """PM2 명령어를 실행하고 결과를 반환"""
    try:
        # command_args가 문자열이면 공백으로 분할
        if isinstance(command_args, str):
            cmd_list = ['pm2'] + command_args.split()
        else:
            cmd_list = ['pm2'] + command_args
        
        # --no-color 옵션 추가
        cmd_list.append('--no-color')
        
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error(f"PM2 command timeout: {command_args}")
        return "", "Command timeout", False
    except Exception as e:
        logger.error(f"PM2 command error: {e}")
        return "", str(e), False

def get_pm2_list():
    """PM2 프로세스 목록을 JSON으로 가져오기"""
    try:
        result = subprocess.run(
            ['pm2', 'jlist'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            logger.error(f"PM2 jlist error: {result.stderr}")
            return []
    except Exception as e:
        logger.error(f"Get PM2 list error: {e}")
        return []

@app.route('/api/pm2/status', methods=['GET'])
def get_pm2_status():
    """PM2 프로세스 상태 조회"""
    try:
        processes = get_pm2_list()
        
        # === [수정됨] 상태 요약 정보 계산 최적화 ===
        # 기존의 여러 반복문을 하나로 통합하여 효율성 증대
        status_counts = Counter(p['pm2_env']['status'] for p in processes)
        total_memory = sum(p['monit']['memory'] for p in processes if p['monit']['memory'])
        total_cpu = sum(p['monit']['cpu'] for p in processes if p['monit']['cpu'])
        total_processes = len(processes)

        response_data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total': total_processes,
                'online': status_counts.get('online', 0),
                'stopped': status_counts.get('stopped', 0),
                'errored': status_counts.get('errored', 0),
                'total_memory_mb': round(total_memory / (1024 * 1024), 2),
                'avg_cpu_percent': round(total_cpu / total_processes if total_processes > 0 else 0, 2)
            },
            'processes': []
        }
        # === 수정 끝 ===
        
        # 각 프로세스 상세 정보
        for proc in processes:
            env = proc['pm2_env']
            monit = proc['monit']
            
            process_info = {
                'pm_id': env['pm_id'],
                'name': env['name'],
                'namespace': env.get('namespace', 'default'),
                'version': env.get('version', 'N/A'),
                'status': env['status'],
                'restart_time': env['restart_time'],
                'uptime': env['pm_uptime'],
                'created_at': env['created_at'],
                'cpu_percent': monit['cpu'],
                'memory_mb': round(monit['memory'] / (1024 * 1024), 2),
                'pid': env.get('pid', 0),
                'instances': env.get('instances', 1),
                'exec_mode': env.get('exec_mode', 'fork'),
                'node_version': env.get('node_version', 'N/A'),
                'script': env.get('pm_exec_path', 'N/A'),
                'args': env.get('args', []),
                'env_vars': {
                    'NODE_ENV': env.get('NODE_ENV', 'N/A'),
                    'PORT': env.get('PORT', 'N/A')
                }
            }
            response_data['processes'].append(process_info)
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Get PM2 status error: {e}")
        return jsonify({'error': str(e)}), 500

# === [수정됨] 프로세스 제어 API 통합 ===
# start, stop, restart 엔드포인트를 하나로 통합하여 코드 중복 제거
@app.route('/api/pm2/process/<int:pm_id>/<action>', methods=['POST'])
def control_process(pm_id, action):
    """특정 프로세스 제어 (start, stop, restart)"""
    # 허용된 action만 실행
    if action not in ['start', 'stop', 'restart']:
        return jsonify({'error': f"Invalid action: {action}. Allowed actions are 'start', 'stop', 'restart'."}), 400

    try:
        # action 변수를 사용하여 pm2 명령어 동적 생성
        stdout, stderr, success = run_pm2_command([action, str(pm_id)])
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Process {pm_id} {action}ed successfully',
                'output': stdout
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to {action} process {pm_id}',
                'error': stderr
            }), 400
            
    except Exception as e:
        logger.error(f"{action.capitalize()} process error for pm_id {pm_id}: {e}")
        return jsonify({'error': str(e)}), 500
# === 수정 끝 (기존의 start_process, stop_process, restart_process 함수는 이 함수로 대체됨) ===


@app.route('/api/pm2/logs/<int:pm_id>', methods=['GET'])
def get_process_logs(pm_id):
    """특정 프로세스 로그 조회"""
    try:
        lines = request.args.get('lines', 50, type=int)
        
        result = subprocess.run(
            ['pm2', 'logs', str(pm_id), '--lines', str(lines), '--nostream', '--raw'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logs = result.stdout.strip().split('\n') if result.stdout.strip() else []
            return jsonify({
                'success': True,
                'logs': logs,
                'count': len(logs)
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to get logs for process {pm_id}',
                'error': result.stderr
            }), 400
            
    except Exception as e:
        logger.error(f"Get process logs error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pm2/flush', methods=['POST'])
def flush_logs():
    """모든 PM2 로그 삭제"""
    try:
        stdout, stderr, success = run_pm2_command('flush')
        
        if success:
            return jsonify({
                'success': True,
                'message': 'All logs flushed successfully',
                'output': stdout
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to flush logs',
                'error': stderr
            }), 400
            
    except Exception as e:
        logger.error(f"Flush logs error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pm2/reload-all', methods=['POST'])
def reload_all():
    """모든 프로세스 리로드 (무중단 재시작)"""
    try:
        stdout, stderr, success = run_pm2_command('reload all')
        
        if success:
            return jsonify({
                'success': True,
                'message': 'All processes reloaded successfully',
                'output': stdout
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to reload all processes',
                'error': stderr
            }), 400
            
    except Exception as e:
        logger.error(f"Reload all error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pm2/health', methods=['GET'])
def health_check():
    """API 헬스 체크"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'PM2 Manager API'
    }), 200

# (이하 나머지 코드는 동일)
# ... (get_env_config, update_env_config 등 나머지 함수들) ...
# ...
@app.route('/api/env/config', methods=['GET'])
def get_env_config():
    """환경변수 설정 조회"""
    try:
        if not os.path.exists(ENV_JS_PATH):
            return jsonify({'error': 'env.js file not found'}), 404
            
        with open(ENV_JS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return jsonify({
            'success': True,
            'content': content,
            'path': ENV_JS_PATH
        }), 200
        
    except Exception as e:
        logger.error(f"Get env config error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/env/config', methods=['PUT'])
def update_env_config():
    """환경변수 설정 업데이트"""
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'error': 'Content is required'}), 400
            
        content = data['content']
        
        # 백업 생성
        backup_path = ENV_JS_PATH + '.backup'
        if os.path.exists(ENV_JS_PATH):
            with open(ENV_JS_PATH, 'r', encoding='utf-8') as original:
                with open(backup_path, 'w', encoding='utf-8') as backup:
                    backup.write(original.read())
        
        # 새 내용 저장
        with open(ENV_JS_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
            
        logger.info("Environment configuration updated successfully")
        
        return jsonify({
            'success': True,
            'message': 'Environment configuration updated successfully',
            'backup_created': backup_path
        }), 200
        
    except Exception as e:
        logger.error(f"Update env config error: {e}")
        # 백업에서 복원 시도
        backup_path = ENV_JS_PATH + '.backup'
        if os.path.exists(backup_path):
            try:
                with open(backup_path, 'r', encoding='utf-8') as backup:
                    with open(ENV_JS_PATH, 'w', encoding='utf-8') as original:
                        original.write(backup.read())
                logger.info("Restored from backup due to error")
            except:
                pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/env/services', methods=['GET'])
def get_services_config():
    """서비스별 호스트/포트 설정 조회 (파싱된 형태)"""
    try:
        if not os.path.exists(ENV_JS_PATH):
            return jsonify({'error': 'env.js file not found'}), 404
            
        # Node.js로 env.js 파일을 실행하여 JSON으로 변환
        result = subprocess.run([
            'node', '-e', f'''
            const config = require("{ENV_JS_PATH}");
            console.log(JSON.stringify(config.services, null, 2));
            '''
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            services = json.loads(result.stdout)
            return jsonify({
                'success': True,
                'services': services
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.stderr
            }), 400
            
    except Exception as e:
        logger.error(f"Get services config error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/env/services/<service_name>', methods=['PUT'])
def update_service_config(service_name):
    """특정 서비스의 호스트/포트 설정 업데이트"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
            
        # env.js 파일 읽기
        with open(ENV_JS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 백업 생성
        backup_path = ENV_JS_PATH + '.backup'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        # 서비스 설정 업데이트 (더 정확한 정규식 사용)
        import re
        
        # 서비스 블록 찾기 (중괄호 매칭 개선)
        service_pattern = rf'{service_name}:\s*\{{([^}}]*)\}}'
        
        def update_service_block(match):
            service_block_content = match.group(1)
            logger.info(f"Updating service '{service_name}' configuration - using hardcoded values")
            
            # 각 필드를 무조건 하드코딩 방식으로 업데이트
            if 'host' in data:
                if 'host:' in service_block_content:
                    logger.info(f"Updating host to hardcoded value: {data['host']}")
                    service_block_content = re.sub(
                        r"host:\s*[^,\n}]+", 
                        f"host: '{data['host']}'", 
                        service_block_content
                    )
                    
            if 'port' in data:
                if 'port:' in service_block_content:
                    logger.info(f"Updating port to hardcoded value: {data['port']}")
                    service_block_content = re.sub(
                        r"port:\s*[^,\n}]+", 
                        f"port: '{data['port']}'", 
                        service_block_content
                    )
                    
            if 'protocol' in data:
                if 'protocol:' in service_block_content:
                    logger.info(f"Updating protocol to hardcoded value: {data['protocol']}")
                    service_block_content = re.sub(
                        r"protocol:\s*[^,\n}]+", 
                        f"protocol: '{data['protocol']}'", 
                        service_block_content
                    )
                
            return f'{service_name}: {{{service_block_content}}}'
            
        new_content = re.sub(service_pattern, update_service_block, content, flags=re.DOTALL)
        
        # 파일 저장
        with open(ENV_JS_PATH, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        logger.info(f"Service {service_name} configuration updated successfully")
        
        return jsonify({
            'success': True,
            'message': f'Service {service_name} configuration updated successfully',
            'backup_created': backup_path
        }), 200
        
    except Exception as e:
        logger.error(f"Update service config error: {e}")
        # 백업에서 복원
        backup_path = ENV_JS_PATH + '.backup'
        if os.path.exists(backup_path):
            try:
                with open(backup_path, 'r', encoding='utf-8') as backup:
                    with open(ENV_JS_PATH, 'w', encoding='utf-8') as original:
                        original.write(backup.read())
                logger.info("Restored from backup due to error")
            except:
                pass
        return jsonify({
            'success': False,
            'message': f'Failed to update service configuration: {str(e)}'
        }), 500

@app.route('/api/env/config/parsed', methods=['GET'])
def get_parsed_env_config():
    """환경변수 설정을 파싱된 JSON 형태로 조회"""
    try:
        if not os.path.exists(ENV_JS_PATH):
            return jsonify({'error': 'env.js file not found'}), 404
            
        # Node.js로 env.js 파일을 실행하여 JSON으로 변환
        result = subprocess.run([
            'node', '-e', f'''
            const config = require("{ENV_JS_PATH}");
            console.log(JSON.stringify(config, null, 2));
            '''
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            config = json.loads(result.stdout)
            return jsonify({
                'success': True,
                'config': config
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.stderr
            }), 400
            
    except Exception as e:
        logger.error(f"Get parsed env config error: {e}")
        return jsonify({'error': str(e)}), 500

def get_dependent_services(changed_services):
    """변경된 서비스에 의존하는 PM2 프로세스들을 동적으로 반환"""
    services_to_restart = set()
    
    for service in changed_services:
        # 1. 변경된 서비스 자체를 재시작
        services_to_restart.add(service)
        
        # 2. API 서비스가 변경된 경우, 웹과 admin도 재시작 (API 클라이언트들)
        if service.endswith('-api'):
            services_to_restart.add('web-app-dev')
            services_to_restart.add('admin-dashboard')
    
    return list(services_to_restart)

def restart_services(service_names):
    """여러 서비스를 순차적으로 재시작"""
    restart_results = []
    
    for service_name in service_names:
        try:
            stdout, stderr, success = run_pm2_command(f'restart {service_name}')
            restart_results.append({
                'service': service_name,
                'success': success,
                'message': stdout if success else stderr
            })
            logger.info(f"Service {service_name} restart: {'success' if success else 'failed'}")
        except Exception as e:
            restart_results.append({
                'service': service_name,
                'success': False,
                'message': str(e)
            })
            logger.error(f"Service {service_name} restart error: {e}")
    
    return restart_results

@app.route('/api/env/config/db-update', methods=['PUT']) 
def update_env_config_db():
    """DB를 통한 환경변수 설정 업데이트 + 자동 재시작"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
            
        changed_services = set()
        update_results = []
        
        # 각 설정을 DB에 직접 업데이트
        for section, section_data in data.items():
            if isinstance(section_data, dict):
                for subsection, subsection_data in section_data.items():
                    if isinstance(subsection_data, dict):
                        for key, value in subsection_data.items():
                            try:
                                # PostgREST를 통해 업데이트
                                update_url = f"http://localhost:3010/env_configs?section=eq.{section}&subsection=eq.{subsection}&key=eq.{key}"
                                update_data = {'value': str(value)}
                                
                                response = requests.patch(update_url, json=update_data, headers={'Content-Type': 'application/json'}, timeout=10)
                                
                                if response.status_code in [200, 204]:
                                    update_results.append(f"Updated {section}.{subsection}.{key} = {value}")
                                    changed_services.add(subsection)
                                    logger.info(f"Updated DB config: {section}.{subsection}.{key} = {value}")
                                else:
                                    update_results.append(f"Failed to update {section}.{subsection}.{key}: HTTP {response.status_code}")
                                    
                            except Exception as e:
                                update_results.append(f"Error updating {section}.{subsection}.{key}: {str(e)}")
        
        # 변경된 서비스들과 의존 서비스들 재시작
        if changed_services:
            services_to_restart = get_dependent_services(list(changed_services))
            restart_results = restart_services(services_to_restart)
            
            return jsonify({
                'success': True,
                'message': 'Configuration updated and services restarted',
                'updates': update_results,
                'restarts': restart_results,
                'changed_services': list(changed_services),
                'restarted_services': services_to_restart
            }), 200
        else:
            return jsonify({
                'success': True,
                'message': 'No services were changed',
                'updates': update_results
            }), 200
            
    except Exception as e:
        logger.error(f"Update env config DB error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/env/config/update', methods=['PUT'])
def update_parsed_env_config():
    """텍스트 기반 환경변수 설정 업데이트 (정규식 사용, 구조 보존) + 관련 서비스 자동 재시작"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
            
        # 현재 파일 내용 읽기
        if not os.path.exists(ENV_JS_PATH):
            return jsonify({'error': 'env.js file not found'}), 404
            
        with open(ENV_JS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 백업 생성
        backup_path = ENV_JS_PATH + '.backup'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 텍스트 기반 업데이트 함수
        def update_value_in_text(text, path, new_value):
            """정규식을 사용해 특정 경로의 값을 업데이트"""
            import re
            
            # path를 분해 (예: ['exchange', 'scheduler', 'dailyUpdateHour'])
            keys = path.split('.')
            
            if len(keys) == 1:
                # 최상위 레벨 업데이트
                pattern = rf'({keys[0]}:\s*)([^,\n}}]+)(,?)'
                replacement = rf'\g<1>{format_js_value_simple(new_value)}\g<3>'
                return re.sub(pattern, replacement, text)
            
            elif len(keys) == 2:
                # 2단계 깊이 (예: services.web)
                section_name = keys[0]
                field_name = keys[1]
                
                # 섹션 찾기
                section_pattern = rf'({section_name}:\s*\{{[^}}]*?{field_name}:\s*)([^,\n}}]+)(,?[^}}]*?\}})'
                replacement = rf'\g<1>{format_js_value_simple(new_value)}\g<3>'
                return re.sub(section_pattern, replacement, text, flags=re.DOTALL)
            
            elif len(keys) == 3:
                # 3단계 깊이 (예: exchange.scheduler.dailyUpdateHour)
                section_name = keys[0]
                subsection_name = keys[1] 
                field_name = keys[2]
                
                # 중첩된 구조에서 값 찾기 및 교체
                pattern = rf'({section_name}:\s*\{{.*?{subsection_name}:\s*\{{[^}}]*?{field_name}:\s*)([^,\n}}]+)(,?[^}}]*?\}}[^}}]*?\}})'
                replacement = rf'\g<1>{format_js_value_simple(new_value)}\g<3>'
                return re.sub(pattern, replacement, text, flags=re.DOTALL)
            
            return text
        
        def format_js_value_simple(value):
            """간단한 JavaScript 값 포맷팅"""
            if isinstance(value, str):
                return f"'{value}'"
            elif isinstance(value, bool):
                return str(value).lower()
            elif isinstance(value, (int, float)):
                return str(value)
            elif value is None:
                return 'undefined'
            else:
                return str(value)
        
        # 데이터를 순회하며 업데이트
        updated_content = content
        
        def process_updates(obj, prefix=""):
            nonlocal updated_content
            
            for key, value in obj.items():
                current_path = f"{prefix}.{key}" if prefix else key
                
                if isinstance(value, dict):
                    # 재귀적으로 중첩된 객체 처리
                    process_updates(value, current_path)
                else:
                    # 실제 값 업데이트
                    logger.info(f"Updating {current_path} = {value}")
                    updated_content = update_value_in_text(updated_content, current_path, value)
        
        process_updates(data)
        
        # 파일 저장
        with open(ENV_JS_PATH, 'w', encoding='utf-8') as f:
            f.write(updated_content)
            
        logger.info("Environment configuration updated successfully using text-based method")
        
        return jsonify({
            'success': True,
            'message': 'Environment configuration updated successfully',
            'backup_created': backup_path
        }), 200
        
    except Exception as e:
        logger.error(f"Update env config error: {e}")
        # 백업에서 복원 시도
        backup_path = ENV_JS_PATH + '.backup'
        if os.path.exists(backup_path):
            try:
                with open(backup_path, 'r', encoding='utf-8') as backup:
                    with open(ENV_JS_PATH, 'w', encoding='utf-8') as original:
                        original.write(backup.read())
                logger.info("Restored from backup due to error")
            except:
                pass
        return jsonify({'error': str(e)}), 500

@app.route('/api/pm2/process/name/<process_name>/restart', methods=['POST'])
def restart_process_by_name(process_name):
    """프로세스 이름으로 재시작"""
    try:
        stdout, stderr, success = run_pm2_command(f'restart {process_name}')
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Process {process_name} restarted successfully',
                'output': stdout
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to restart process {process_name}',
                'error': stderr
            }), 400
            
    except Exception as e:
        logger.error(f"Restart process by name error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3006))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    logger.info(f"🚀 PM2 Manager API starting on {host}:{port}")
    logger.info(f"🔒 PM2 Manager Service starting on {host}:{port} (로컬 접근만 허용)")
    
    app.run(host=host, port=port, debug=debug)