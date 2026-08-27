# v2 因子库增强选股组合 — 聚宽在线 IDE 版（白名单定稿版）
# 来源: github.com/Moliseeee/quant v2 研究草案
# 用途: 在聚宽在线回测里直接复制运行，挖 jqfactor 因子库形成 v2 候选组合
#
# 白名单依据（2026-08-27 探针 factor_whitelist_probe.py 实测）:
#   - style_pro 类 16 因子（divyild/earnqlty/profit/resvol/btop 等）线上全部
#     "无效的因子" → 本版不包含任何 style_pro 因子
#   - quality/basics/growth/emotion/risk/momentum 六类全有效（non_na=50/50 实测）
#   - 高股息改用 finance 分红表手动计算（每股分红/股价，替代 divyild）
#
# 重要纪律：
#   1. 这是"研究候选版"，不是实盘加仓依据；跑完要把结果导出再做分年/持仓归因。
#   2. 默认按"纯策略研究"口径：Top20、周频、行业≤5、无最低 5 元佣金。
#      若要和 v1 聚宽结果直接对照，把 g.N 改 8、g.MAX_PER_INDUSTRY 改 3、min_commission 改 5。
#   3. 所有财务/估值数据显式使用 context.previous_date，避免未来函数。
#   4. jqfactor 批量拉取失败时，单因子降级为中性分并写日志，不让策略静默零成交。
#
# 推荐回测设置：
#   区间: 2020-01-02 ~ 2026-08-25
#   频率: 日频
#   初始资金: 200000
#   基准: 000300.XSHG

from datetime import timedelta


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 纯策略研究口径：不使用小资金最低佣金惩罚；若复现 v1 实盘口径可改 min_commission=5。
    set_order_cost(OrderCost(open_tax=0, close_tax=0.0005,
                             open_commission=0.00025, close_commission=0.00025,
                             close_today_commission=0, min_commission=0), type='stock')
    set_slippage(FixedSlippage(0.02))

    # ===== 核心参数 =====
    g.N = 20
    g.MAX_PER_INDUSTRY = 5
    g.MIN_MARKET_CAP_YI = 50       # valuation.market_cap 单位是"亿元"
    g.week_count = 0

    # v2 白名单定稿因子（全部线上探针确认有效；style_pro 已全部剔除）
    # direction: +1 表示越大越好；-1 表示越小越好；source: valuation / jqfactor / derived / finance
    g.FACTOR_SPECS = [
        # v1 骨架（保留但降权，避免价值族重复下注过重）
        {'name': 'low_turnover', 'source': 'valuation', 'column': 'turnover_ratio', 'direction': -1, 'weight': 0.20,
         'desc': '低换手：v1 最强防御因子'},
        {'name': 'low_pb', 'source': 'valuation', 'column': 'pb_ratio', 'direction': -1, 'weight': 0.12,
         'desc': '低PB'},
        {'name': 'ep', 'source': 'derived', 'column': 'pe_ratio', 'direction': +1, 'weight': 0.08,
         'desc': 'E/P：1/PE，PE<=0 过滤'},
        {'name': 'low_ps', 'source': 'valuation', 'column': 'ps_ratio', 'direction': -1, 'weight': 0.06,
         'desc': '低PS，金融股中性'},

        # 高股息：finance 分红表手动计算（替代线上不支持的 divyild）
        {'name': 'high_dividend', 'source': 'finance', 'column': 'dividend_yield', 'direction': +1, 'weight': 0.10,
         'desc': '股息率=近一年每股分红/股价（finance 分红表手动算）'},

        # 现金流估值
        {'name': 'cash_flow_to_price_ratio', 'source': 'jqfactor', 'column': 'cash_flow_to_price_ratio', 'direction': +1, 'weight': 0.08,
         'desc': '现金流市值比：已缓存近一年 ICIR 约0.40'},
        {'name': 'cfo_to_ev', 'source': 'jqfactor', 'column': 'cfo_to_ev', 'direction': +1, 'weight': 0.05,
         'desc': '经营现金流/EV'},

        # 质量/盈利能力（探针确认有效，替代 style_pro 的 earnqlty/profit）
        {'name': 'roe_ttm', 'source': 'jqfactor', 'column': 'roe_ttm', 'direction': +1, 'weight': 0.08,
         'desc': 'ROE TTM'},
        {'name': 'roa_ttm', 'source': 'jqfactor', 'column': 'roa_ttm', 'direction': +1, 'weight': 0.04,
         'desc': 'ROA TTM'},
        {'name': 'cash_rate_of_sales', 'source': 'jqfactor', 'column': 'cash_rate_of_sales', 'direction': +1, 'weight': 0.05,
         'desc': '销售现金含量'},
        {'name': 'asset_turnover_ttm', 'source': 'jqfactor', 'column': 'asset_turnover_ttm', 'direction': +1, 'weight': 0.04,
         'desc': '资产周转率'},
        {'name': 'debt_to_asset_ratio', 'source': 'jqfactor', 'column': 'debt_to_asset_ratio', 'direction': -1, 'weight': 0.04,
         'desc': '低资产负债率'},

        # 流动性结构/风险（替代 style_pro 的 resvol；探针确认有效）
        {'name': 'DAVOL20', 'source': 'jqfactor', 'column': 'DAVOL20', 'direction': -1, 'weight': 0.04,
         'desc': '20日/120日换手比，越低越冷静'},
        {'name': 'turnover_volatility', 'source': 'jqfactor', 'column': 'turnover_volatility', 'direction': -1, 'weight': 0.04,
         'desc': '换手率波动，越低越稳'},
        {'name': 'Variance120', 'source': 'jqfactor', 'column': 'Variance120', 'direction': -1, 'weight': 0.04,
         'desc': '120日收益方差，低波'},

        # 进攻性小开关：52周位置在本地是牛市区制候选，权重很小，避免动量负alpha反噬
        {'name': 'fifty_two_week_close_rank', 'source': 'jqfactor', 'column': 'fifty_two_week_close_rank', 'direction': +1, 'weight': 0.02,
         'desc': '52周价格位置，牛市补偿项（低权重，A股动量为负alpha）'},
    ]

    run_weekly(rebalance, weekday=-1, time='close')
    run_daily(schedule_probe, time='14:29')
    log.info('INIT_OK v2_whitelist N=%d max_ind=%d factors=%d' %
             (g.N, g.MAX_PER_INDUSTRY, len(g.FACTOR_SPECS)))


def schedule_probe(context):
    log.info('DAILY_PROBE ' + str(context.current_dt)[:19])


def rebalance(context):
    g.week_count += 1
    log.info('REBALANCE_CALLED week=%d date=%s' % (g.week_count, str(context.current_dt)[:19]))
    rebalance_impl(context)


def rebalance_impl(context):
    data_date = context.previous_date

    # 1) 基础股票池：字段只使用聚宽线上 valuation 已确认字段。
    q = query(valuation.code,
              valuation.pe_ratio, valuation.pb_ratio, valuation.ps_ratio,
              valuation.turnover_ratio, valuation.market_cap).filter(
        valuation.pe_ratio > 0,
        valuation.pb_ratio > 0,
        valuation.ps_ratio > 0,
        valuation.turnover_ratio > 0,
        valuation.market_cap > g.MIN_MARKET_CAP_YI
    )
    raw = get_fundamentals(q, date=data_date)
    log.info('POOL_RAW date=%s rows=%d' % (data_date, len(raw)))
    if len(raw) < g.N * 3:
        log.warn('POOL_TOO_SMALL rows=%d' % len(raw))
        return

    df = raw.dropna(subset=['pe_ratio', 'pb_ratio', 'ps_ratio', 'turnover_ratio', 'market_cap']).set_index('code')

    # 2) 当前可交易过滤：停牌/ST 先剔除，减少 jqfactor 请求量和无效打分。
    current_data = get_current_data()
    tradable_index = []
    for code in list(df.index):
        try:
            cd = current_data[code]
            if (not cd.paused) and (not cd.is_st):
                tradable_index.append(code)
        except Exception:
            pass
    df = df.loc[tradable_index]
    log.info('POOL_TRADABLE rows=%d' % len(df))
    if len(df) < g.N * 3:
        log.warn('TRADABLE_TOO_SMALL rows=%d' % len(df))
        return

    # 3) 拉 jqfactor 因子。失败因子会中性化，不会造成整场回测中断。
    jq_cols = []
    for spec in g.FACTOR_SPECS:
        if spec['source'] == 'jqfactor' and spec['column'] not in jq_cols:
            jq_cols.append(spec['column'])
    jq_values = fetch_jqfactor_values(list(df.index), jq_cols, data_date)
    for col in jq_cols:
        if col in jq_values:
            df[col] = jq_values[col].reindex(df.index)
        else:
            df[col] = None

    # 3.1) 高股息：finance 分红表手动算（每股分红/股价）
    div_spec = [s for s in g.FACTOR_SPECS if s['source'] == 'finance']
    if div_spec:
        df['dividend_yield'] = compute_dividend_yield(list(df.index), df['market_cap'], data_date)
        log.info('DIVIDEND_YIELD non_na=%d' % int(df['dividend_yield'].notna().sum()))

    # 4) 行业映射：用于行业上限、金融股 PS 中性。
    industry_map = get_industry_map(list(df.index), data_date)

    # 5) 合成打分。
    df['score'] = 0.0
    active_weight = 0.0
    detail = []
    for spec in g.FACTOR_SPECS:
        s = build_factor_series(df, spec)
        if s is None:
            log.warn('FACTOR_SKIP name=%s reason=no_series' % spec['name'])
            continue
        r = rank_score(s, spec['direction'])

        # 金融股 PS 口径特殊：置中性 0.5，沿用 v1 纪律。
        if spec['name'] == 'low_ps':
            r = neutralize_financial_ps(r, industry_map)

        non_neutral = int((r != 0.5).sum())
        if non_neutral < g.N * 2:
            log.warn('FACTOR_WEAK name=%s non_neutral=%d; still used with many neutral values' %
                     (spec['name'], non_neutral))
        df['score'] += spec['weight'] * r
        active_weight += spec['weight']
        detail.append('%s(w=%.2f,n=%d)' % (spec['name'], spec['weight'], non_neutral))
    log.info('FACTOR_ACTIVE weight=%.2f detail=%s' % (active_weight, '; '.join(detail)))

    if active_weight <= 0:
        log.warn('NO_ACTIVE_FACTOR')
        return

    df = df.sort_values('score', ascending=False)

    # 6) TopN + 行业≤K 贪心。
    picked = []
    counts = {}
    for code in df.index:
        if len(picked) >= g.N:
            break
        ind_name = industry_map.get(code, 'UNKNOWN_' + code)
        if counts.get(ind_name, 0) >= g.MAX_PER_INDUSTRY:
            continue
        counts[ind_name] = counts.get(ind_name, 0) + 1
        picked.append(code)
    if not picked:
        log.warn('NO_PICKED')
        return

    log.info('PICKED n=%d codes=%s' % (len(picked), picked))
    log.info('PICKED_INDUSTRY %s' % str(counts))
    log.info('PICKED_SCORE_TOP %s' % str([(c, round(float(df.loc[c, 'score']), 4)) for c in picked[:10]]))

    # 7) 等权调仓：先卖后买。
    target_set = set(picked)
    for code in list(context.portfolio.positions.keys()):
        if code not in target_set:
            order_target_value(code, 0)
    target_value = context.portfolio.total_value / len(picked)
    for code in picked:
        order = order_target_value(code, target_value)
        log.info('ORDER code=%s target=%.0f result=%s' % (code, target_value, str(order)))


def compute_dividend_yield(codes, market_cap_series, data_date):
    """用 finance 分红表手动计算股息率（每股分红/股价），替代线上不支持的 divyild。

    取近一年（365 天）内公告的现金分红，累计每股分红，除以当前收盘价。
    无分红/取不到 = NaN（打分中性 0.5）。polywidth finance 表字段：
    dividend_ratio（每股派息）或 cash_div（现金分红总额）视版本而定。
    """
    result = {}
    try:
        from jqdata import finance
        q = query(finance.STK_DIVIDEND).filter(
            finance.STK_DIVIDEND.code.in_(codes),
            finance.STK_DIVIDEND.pay_date >= data_date - timedelta(days=365),
            finance.STK_DIVIDEND.pay_date <= data_date,
            finance.STK_DIVIDEND.dividend_ratio > 0
        )
        div = finance.run_query(q)
        if div is not None and len(div) > 0:
            for code, grp in div.groupby('code'):
                per_share = grp['dividend_ratio'].sum()  # 每股派息（元）
                price = get_price(code, end_date=data_date, count=1, fields=['close'])
                if price is not None and len(price) > 0:
                    px = float(price['close'].iloc[-1])
                    if px and px > 0:
                        result[code] = per_share / px
    except Exception as e:
        log.warn('DIVIDEND_FINANCE_FAILED err=%s' % str(e)[:160])
    import pandas as pd
    return pd.Series(result).reindex(codes)


def fetch_jqfactor_values(codes, factors, data_date):
    """返回 {factor: Series(code->value)}；按小批量拉，避免单次因子过多失败。"""
    result = {}
    if not factors:
        return result
    try:
        from jqfactor import get_factor_values
    except Exception as e:
        log.warn('IMPORT_JQFACTOR_FAILED %s' % str(e)[:120])
        return result

    batch_size = 6
    for i in range(0, len(factors), batch_size):
        batch = factors[i:i + batch_size]
        try:
            fv = get_factor_values(securities=codes, factors=batch, end_date=data_date, count=1)
            for name in batch:
                if fv and name in fv and len(fv[name]) > 0:
                    result[name] = fv[name].iloc[-1]
                    log.info('JQFACTOR_OK %s non_na=%d' % (name, int(result[name].count())))
                else:
                    log.warn('JQFACTOR_EMPTY %s' % name)
        except Exception as e:
            log.warn('JQFACTOR_BATCH_FAILED batch=%s err=%s' % (batch, str(e)[:160]))
            # 单因子重试，防止一个坏因子拖垮整批。
            for name in batch:
                try:
                    one = get_factor_values(securities=codes, factors=[name], end_date=data_date, count=1)
                    if one and name in one and len(one[name]) > 0:
                        result[name] = one[name].iloc[-1]
                        log.info('JQFACTOR_OK_SINGLE %s non_na=%d' % (name, int(result[name].count())))
                    else:
                        log.warn('JQFACTOR_EMPTY_SINGLE %s' % name)
                except Exception as e2:
                    log.warn('JQFACTOR_FAILED %s err=%s' % (name, str(e2)[:160]))
    return result


def build_factor_series(df, spec):
    """根据 spec 构造原始因子值。方向由 rank_score 统一处理。"""
    col = spec['column']
    if spec['source'] == 'derived' and spec['name'] == 'ep':
        pe = df['pe_ratio']
        return pe.apply(lambda x: (1.0 / x) if x and x > 0 else None)
    if spec['source'] == 'finance':
        return df[col] if col in df.columns else None
    if col not in df.columns:
        return None
    return df[col]


def rank_score(series, direction):
    """截面百分位分数：0~1；缺失值中性 0.5；direction=-1 表示越小越好。"""
    s = series.dropna()
    if len(s) == 0:
        return series.apply(lambda x: 0.5)
    r = s.rank(pct=True)
    if direction < 0:
        r = 1.0 - r
    out = series.copy()
    out.loc[:] = 0.5
    out.loc[r.index] = r
    return out


def neutralize_financial_ps(score_series, industry_map):
    financial_keys = ['银行', '证券', '保险', '多元金融', '非银金融']
    out = score_series.copy()
    for code in list(out.index):
        ind = industry_map.get(code, '')
        for key in financial_keys:
            if key in ind:
                out.loc[code] = 0.5
                break
    return out


def get_industry_map(codes, date):
    """聚宽行业归属。优先批量，失败则逐只；未知行业不共用桶。"""
    res = {}
    try:
        info = get_industry(codes, date=date)
        for code in codes:
            item = info.get(code, {}) if info else {}
            jq_l1 = item.get('jq_l1')
            if jq_l1:
                res[code] = jq_l1.get('industry_name', 'UNKNOWN_' + code)
            else:
                res[code] = 'UNKNOWN_' + code
        return res
    except Exception as e:
        log.warn('INDUSTRY_BATCH_FAILED err=%s' % str(e)[:120])

    for code in codes:
        try:
            item = get_industry(code, date=date).get(code, {})
            jq_l1 = item.get('jq_l1')
            if jq_l1:
                res[code] = jq_l1.get('industry_name', 'UNKNOWN_' + code)
            else:
                res[code] = 'UNKNOWN_' + code
        except Exception as e:
            log.warn('INDUSTRY_FAILED code=%s err=%s' % (code, str(e)[:120]))
            res[code] = 'UNKNOWN_' + code
    return res
