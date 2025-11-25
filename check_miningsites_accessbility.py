#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查挖矿网站连通性
从 results/mining_sites.txt 读取URL列表，检查连通性，生成 accessible_miningsites.txt
"""

import requests
import time
import logging
from datetime import datetime
from typing import List, Dict
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

# 尝试导入tqdm（进度条库）
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # 简单的文本进度条实现（当tqdm未安装时使用）
    class tqdm:
        def __init__(self, total=None, desc=None, unit=None, bar_format=None):
            self.total = total
            self.desc = desc or ""
            self.unit = unit or "it"
            self.n = 0
            self.last_percent = -1
            self.postfix = {}
        
        def update(self, n=1):
            self.n += n
            if self.total:
                percent = int((self.n / self.total) * 100)
                # 每25%显示一次
                if percent >= 25 and self.last_percent < 25:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 25% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 25
                elif percent >= 50 and self.last_percent < 50:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 50% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 50
                elif percent >= 75 and self.last_percent < 75:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 75% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 75
                elif percent >= 100 and self.last_percent < 100:
                    postfix_str = ", ".join([f"{k}={v}" for k, v in self.postfix.items()])
                    print(f"\n{self.desc}: 100% 完成 ({self.n}/{self.total}) [{postfix_str}]")
                    self.last_percent = 100
        
        def set_postfix(self, *args, **kwargs):
            """设置进度条后缀信息"""
            # 支持字典参数（通过解包）或关键字参数
            if args and isinstance(args[0], dict):
                self.postfix = args[0]
            else:
                self.postfix = kwargs
        
        def __enter__(self):
            return self
        
        def __exit__(self, *args):
            pass
        
        def close(self):
            pass

# 创建输出目录
os.makedirs('logs', exist_ok=True)
os.makedirs('results', exist_ok=True)

# 配置日志
log_file = os.path.join('logs', f'check_miningsites_accessibility_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class MiningSiteAccessibilityChecker:
    """挖矿网站连通性检查器"""
    
    def __init__(self, timeout: int = 10, max_workers: int = 20):
        """
        初始化检查器
        
        Args:
            timeout: 请求超时时间（秒）
            max_workers: 最大并发线程数
        """
        self.timeout = timeout
        self.max_workers = max_workers
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        logger.info(f"初始化检查器: 超时={self.timeout}秒, 并发数={self.max_workers}")
    
    def check_url_accessible(self, url: str) -> Dict:
        """
        检查URL是否可访问
        
        Args:
            url: 要检查的URL
            
        Returns:
            包含访问结果的字典
        """
        result = {
            'url': url,
            'accessible': False,
            'status_code': None,
            'error': None,
            'redirect_url': None,
            'response_time': None
        }
        
        try:
            start_time = time.time()
            
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                verify=False  # 忽略SSL证书错误
            )
            response_time = time.time() - start_time
            
            result['accessible'] = True
            result['status_code'] = response.status_code
            result['response_time'] = round(response_time, 2)
            result['redirect_url'] = response.url if response.url != url else None
            
            # 检查是否是重定向到其他域名
            if result['redirect_url']:
                original_domain = urlparse(url).netloc
                redirect_domain = urlparse(result['redirect_url']).netloc
                if original_domain != redirect_domain:
                    result['redirected'] = True
                    result['redirect_domain'] = redirect_domain
                else:
                    result['redirected'] = False
            else:
                result['redirected'] = False
                
        except requests.exceptions.Timeout:
            result['error'] = 'Timeout'
        except requests.exceptions.ConnectionError:
            result['error'] = 'ConnectionError'
        except requests.exceptions.SSLError:
            result['error'] = 'SSLError'
        except requests.exceptions.RequestException as e:
            result['error'] = str(e)
        except Exception as e:
            result['error'] = f'Unexpected error: {str(e)}'
            
        return result
    
    def check_sites_from_file(self, input_file: str, output_file: str) -> List[Dict]:
        """
        从文本文件读取URL并检查连通性
        
        Args:
            input_file: 输入文件路径（每行一个URL）
            output_file: 输出文件路径（可访问的URL列表）
            
        Returns:
            检查结果列表
        """
        results = []
        urls = []
        
        # 读取URL列表
        logger.info(f"读取URL列表: {input_file}")
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):  # 忽略空行和注释行
                        urls.append(url)
            
            logger.info(f"找到 {len(urls)} 个URL")
        except FileNotFoundError:
            logger.error(f"文件不存在: {input_file}")
            return results
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return results
        
        if len(urls) == 0:
            logger.warning("URL列表为空")
            return results
        
        # 并发检查
        logger.info(f"开始检查，并发数: {self.max_workers}, 超时: {self.timeout}秒")
        accessible_count = 0
        
        # 创建进度条
        progress_desc = "检查网站连通性"
        with tqdm(total=len(urls), desc=progress_desc, unit="个", 
                  bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_url = {
                    executor.submit(self.check_url_accessible, url): url 
                    for url in urls
                }
                
                completed = 0
                last_logged_percent = -1
                
                for future in as_completed(future_to_url):
                    completed += 1
                    url = future_to_url[future]
                    
                    try:
                        result = future.result()
                        results.append(result)
                        
                        if result['accessible']:
                            accessible_count += 1
                            logger.info(f"[OK] {url} - 可访问 (状态码: {result['status_code']}, 响应时间: {result['response_time']}s)")
                        else:
                            logger.debug(f"[FAIL] {url} - 不可访问: {result['error']}")
                        
                        # 更新进度条
                        pbar.update(1)
                        # 防止除零错误
                        success_rate = (accessible_count/completed*100) if completed > 0 else 0.0
                        pbar.set_postfix({
                            '可访问': accessible_count,
                            '成功率': f'{success_rate:.1f}%'
                        })
                        
                        # 每25%显示一次详细进度（25%, 50%, 75%, 100%）
                        current_percent = int((completed / len(urls)) * 100)
                        percent_milestones = [25, 50, 75, 100]
                        for milestone in percent_milestones:
                            if current_percent >= milestone and last_logged_percent < milestone:
                                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                                # 防止除零错误
                                success_rate = (accessible_count/completed*100) if completed > 0 else 0.0
                                logger.info(f"进度: {milestone}% ({completed}/{len(urls)}) - "
                                          f"可访问: {accessible_count}, "
                                          f"成功率: {success_rate:.1f}%")
                                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                                last_logged_percent = milestone
                                break
                            
                    except Exception as e:
                        logger.error(f"检查 {url} 时出错: {e}")
                        results.append({
                            'url': url,
                            'accessible': False,
                            'error': str(e),
                            'checked_at': datetime.now().isoformat()
                        })
                        pbar.update(1)
        
        # 保存可访问的网站列表
        accessible_urls = [r['url'] for r in results if r['accessible']]
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for url in accessible_urls:
                    f.write(f"{url}\n")
            
            logger.info(f"可访问网站列表已保存到: {output_file}")
            logger.info(f"共 {len(accessible_urls)} 个可访问的网站")
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
        
        # 统计信息
        logger.info("="*60)
        logger.info("检查完成！")
        logger.info(f"总URL数: {len(urls)}")
        logger.info(f"可访问: {accessible_count}")
        logger.info(f"不可访问: {len(urls) - accessible_count}")
        # 防止除零错误
        success_rate = (accessible_count/len(urls)*100) if len(urls) > 0 else 0.0
        logger.info(f"成功率: {success_rate:.1f}%")
        logger.info("="*60)
        
        return results


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='检查挖矿网站连通性')
    parser.add_argument('-i', '--input', default='results/mining_sites.txt',
                       help='输入文件路径（每行一个URL）(默认: results/mining_sites.txt)')
    parser.add_argument('-o', '--output', default='results/accessible_miningsites.txt',
                       help='输出文件路径（可访问的URL列表）(默认: results/accessible_miningsites.txt)')
    parser.add_argument('-t', '--timeout', type=int, default=10,
                       help='请求超时时间（秒）(默认: 10)')
    parser.add_argument('-w', '--workers', type=int, default=20,
                       help='最大并发线程数 (默认: 20)')
    
    args = parser.parse_args()
    
    # 确保输出目录存在
    output_dir = os.path.dirname(args.output) if os.path.dirname(args.output) else 'results'
    os.makedirs(output_dir, exist_ok=True)
    
    # 禁用SSL警告
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # 创建检查器
    checker = MiningSiteAccessibilityChecker(
        timeout=args.timeout, 
        max_workers=args.workers
    )
    
    # 检查网站
    results = checker.check_sites_from_file(args.input, args.output)
    
    logger.info(f"\n输出文件:")
    logger.info(f"  - 可访问网站列表: {args.output}")
    logger.info(f"  - 日志文件: {log_file}")


if __name__ == "__main__":
    main()

