# alpha101/alpha191 全量白名单探针 — 聚宽在线 IDE 版
# 用途: 确认线上 get_factor_values 支持哪些 alpha 因子名（alpha_001 ~ alpha_191）
# 用法: 新建策略 → 粘贴本文件 → 区间选 2023-01-01 ~ 2023-02-01（快）→ 运行 → 看日志
# 预期: ALPHA_OK_COUNT=N + ALPHA_FAIL=[...] 一行汇总，不用翻几百行日志
#
# 背景（2026-08-27）:
#   - 用户发现 jqdatasdk 有 get_all_alpha_101/191 批量接口（本地 SDK）
#   - 首轮探针确认线上 get_factor_values 支持 alpha_001/002/101/102（non_na=50）
#   - 本探针把 alpha_001~alpha_191 全部测一遍，输出 OK 数量 + FAIL 清单

from jqfactor import get_factor_values


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    run_daily(probe, time='14:30')
    log.info('ALPHA_PROBE_INIT_OK')


def probe(context):
    codes = get_index_stocks('000300.XSHG', date=context.previous_date)[:50]
    alpha_names = ['alpha_%03d' % i for i in range(1, 192)]  # alpha_001 ~ alpha_191
    ok_list, fail_list = [], []

    # 分批（每批 20 个因子 × 50 股 = 1000 条数据，远低于请求上限）
    for i in range(0, len(alpha_names), 20):
        batch = alpha_names[i:i + 20]
        try:
            fv = get_factor_values(securities=codes, factors=batch,
                                   end_date=context.previous_date, count=1)
            for name in batch:
                if fv and name in fv and len(fv[name]) > 0:
                    ok_list.append(name)
                else:
                    fail_list.append(name)
        except Exception:
            # 整批失败 → 逐个重试，防一个坏因子拖垮整批
            for name in batch:
                try:
                    fv2 = get_factor_values(securities=codes, factors=[name],
                                            end_date=context.previous_date, count=1)
                    if fv2 and name in fv2 and len(fv2[name]) > 0:
                        ok_list.append(name)
                    else:
                        fail_list.append(name)
                except Exception:
                    fail_list.append(name)

    log.info('ALPHA_OK_COUNT=%d' % len(ok_list))
    log.info('ALPHA_OK_SAMPLE=%s' % str(ok_list[:30]))
    log.info('ALPHA_FAIL_COUNT=%d' % len(fail_list))
    log.info('ALPHA_FAIL=%s' % str(fail_list[:60]))
    log.info('ALPHA_PROBE_DONE')
