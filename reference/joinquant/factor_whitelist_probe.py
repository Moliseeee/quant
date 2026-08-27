# 因子白名单探针 — 聚宽在线 IDE 版
# 用途: 确认线上 get_factor_values 到底支持哪些因子（v2 报 divyild/earnqlty/profit/resvol 无效）
# 用法: 新建策略 → 粘贴本文件 → 区间选 2024-01-01 ~ 2024-03-01（快）→ 运行 → 看日志
# 预期: 直接打印每个因子的 non_na 数，一目了然
#
# 修复记录 2026-08-27:
#   get_factor_values 必须从 jqfactor 导入（线上策略里不是全局内置函数，直接调用会
#   NameError: name 'get_factor_values' is not defined —— 与 v2 主策略里的
#   from jqfactor import get_factor_values 保持一致）。

from jqfactor import get_factor_values


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    run_daily(probe, time='14:30')
    log.info('PROBE_INIT_OK')


def probe(context):
    codes = get_index_stocks('000300.XSHG', date=context.previous_date)[:50]

    # 待测因子分组（按类别，每组单独请求，避免一个失败拖垮整批）
    groups = {
        'style_pro': ['divyild', 'earnqlty', 'profit', 'resvol', 'btop', 'earnyild',
                      'liquidty', 'market_beta', 'market_size', 'midcap', 'ltrevrsl',
                      'relative_momentum', 'financial_leverage', 'invsqlty',
                      'long_growth', 'earnvar'],
        'quality': ['roe_ttm', 'roa_ttm', 'roic_ttm', 'cash_rate_of_sales',
                    'asset_turnover_ttm', 'debt_to_asset_ratio', 'gross_income_ratio',
                    'profit_margin_ttm'],
        'basics': ['cash_flow_to_price_ratio', 'sales_to_price_ratio',
                   'eps_ttm', 'net_profit_ttm'],
        'growth': ['net_profit_growth_rate', 'operating_revenue_growth_rate', 'PEG'],
        'emotion': ['DAVOL20', 'turnover_volatility', 'PSY', 'VR'],
        'risk': ['Variance120', 'Skewness60', 'Kurtosis60', 'sharpe_ratio_120'],
        'momentum': ['fifty_two_week_close_rank', 'BIAS20', 'Price3M'],
    }

    for cat, factors in groups.items():
        for f in factors:
            try:
                fv = get_factor_values(securities=codes, factors=[f],
                                       end_date=context.previous_date, count=1)
                if fv and f in fv and len(fv[f]) > 0:
                    s = fv[f].iloc[-1]
                    log.info('FACTOR_OK %s|%s non_na=%d' % (cat, f, int(s.count())))
                else:
                    log.warn('FACTOR_EMPTY %s|%s' % (cat, f))
            except Exception as e:
                log.warn('FACTOR_FAIL %s|%s err=%s' % (cat, f, str(e)[:80]))
        log.info('GROUP_DONE %s' % cat)

    # 补充: alpha101/alpha191 因子名测试（线上 jqfactor 是否支持）
    alpha_names = ['alpha_001', 'alpha_002', 'alpha_101', 'alpha_102']
    for f in alpha_names:
        try:
            fv = get_factor_values(securities=codes, factors=[f],
                                   end_date=context.previous_date, count=1)
            if fv and f in fv and len(fv[f]) > 0:
                s = fv[f].iloc[-1]
                log.info('FACTOR_OK alpha|%s non_na=%d' % (f, int(s.count())))
            else:
                log.warn('FACTOR_EMPTY alpha|%s' % f)
        except Exception as e:
            log.warn('FACTOR_FAIL alpha|%s err=%s' % (f, str(e)[:80]))

    log.info('PROBE_DONE')
