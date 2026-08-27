# v2 因子库增强选股组合 — 聚宽在线 IDE 版
# 来源: github.com/Moliseeee/quant v1.0.1 后续研究草案
# 用途: 在聚宽在线回测里直接复制运行，挖 jqfactor 因子库形成 v2 候选组合
#
# 重要纪律：
#   1. 这是“研究候选版”，不是实盘加仓依据；跑完要把结果导出再做分年/持仓归因。
#   2. 默认按“纯策略研究”口径：Top20、周频、行业≤5、无最低 5 元佣金。
#      若要和 v1 聚宽结果直接对照，把 g.N 改 8、g.MAX_PER_INDUSTRY 改 3、min_commission 改 5。
#   3. 所有财务/估值数据显式使用 context.previous_date，避免未来函数。
#   4. jqfactor 批量拉取失败时，单因子降级为中性分并写日志，不让策略静默零成交。
#
# 修正记录 2026-08-27（style_pro 线上全灭，探针实测 16/16 无效）:
#   - divyild（高股息 0.10）→ finance.STK_DIVIDEND 分红表手动算（compute_dividend_yield）
#   - earnqlty（盈利质量 0.05）→ profit_margin_ttm（销售净利率TTM）
#   - profit（盈利能力 0.04）→ gross_income_ratio（销售毛利率）
#   - resvol（残差波动 0.03）→ sharpe_ratio_120（120日夏普，方向 +1 越大越好）
#   其余 15 因子全部为探针确认可用的 quality/basics/emotion/risk/momentum 类。
#   白名单实测依据见 会审对话/alpha101_191因子接入方案_20260827.md + 因子使用地图_v2白名单_20260827.md
#
# 推荐回测设置：
#   区间: 2020-01-02 ~ 2026-08-25
#   频率: 日频
#   初始资金: 200000
#   基准: 000300.XSHG


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
    g.MIN_MARKET_CAP_YI = 50       # valuation.market_cap 单位是“亿元”
    g.week_count = 0

    # v2 因子分层：v1 价值/低换手为底仓 + jqfactor 现金流/质量/低波/52周位置增强。
    # direction: +1 表示越大越好；-1 表示越小越好；source: valuation / jqfactor / derived。
    g.FACTOR_SPECS = [
        # v1 骨架（保留但降权，避免价值族重复下注过重）
        {'name': 'low_turnover', 'source': 'valuation', 'column': 'turnover_ratio', 'direction': -1, 'weight': 0.22,
         'desc': '低换手：v1 最强防御因子'},
        {'name': 'low_pb', 'source': 'valuation', 'column': 'pb_ratio', 'direction': -1, 'weight': 0.12,
         'desc': '低PB'},
        {'name': 'ep', 'source': 'derived', 'column': 'pe_ratio', 'direction': +1, 'weight': 0.08,
         'desc': 'E/P：1/PE，PE<=0 过滤'},
        {'name': 'low_ps', 'source': 'valuation', 'column': 'ps_ratio', 'direction': -1, 'weight': 0.06,
         'desc': '低PS，金融股中性'},
        # 高股息：finance 分红表手动计算（2026-08-27 修正：divyild 属 style_pro，线上 get_factor_values 不支持）
        {'name': 'high_dividend', 'source': 'finance', 'column': 'dividend_yield', 'direction': +1, 'weight': 0.10,
         'desc': '股息率=近一年每股分红/股价（finance 分红表手动算，替代 divyild）'},

        # 已有近一年海选信号：cash_flow_to_price_ratio ICIR≈0.40（未中性化，仅作候选）
        {'name': 'cash_flow_to_price_ratio', 'source': 'jqfactor', 'column': 'cash_flow_to_price_ratio', 'direction': +1, 'weight': 0.10,
         'desc': '现金流市值比：已缓存近一年 ICIR 约0.40'},
        {'name': 'cfo_to_ev', 'source': 'jqfactor', 'column': 'cfo_to_ev', 'direction': +1, 'weight': 0.06,
         'desc': '经营现金流/EV'},
        {'name': 'sales_to_price_ratio', 'source': 'jqfactor', 'column': 'sales_to_price_ratio', 'direction': +1, 'weight': 0.04,
         'desc': '营收市值比'},

        # 质量/盈利能力：给小权重，防“低估值陷阱”；不重押成长（本地 profit_yoy 组合层失败）
        # 2026-08-27 修正：earnqlty/profit 属 style_pro 线上不支持，换 profit_margin_ttm/gross_income_ratio
        {'name': 'profit_margin_ttm', 'source': 'jqfactor', 'column': 'profit_margin_ttm', 'direction': +1, 'weight': 0.05,
         'desc': '销售净利率TTM（替代 earnqlty）'},
        {'name': 'gross_income_ratio', 'source': 'jqfactor', 'column': 'gross_income_ratio', 'direction': +1, 'weight': 0.04,
         'desc': '销售毛利率（替代 profit）'},
        {'name': 'roe_ttm', 'source': 'jqfactor', 'column': 'roe_ttm', 'direction': +1, 'weight': 0.04,
         'desc': 'ROE TTM'},
        {'name': 'cash_rate_of_sales', 'source': 'jqfactor', 'column': 'cash_rate_of_sales', 'direction': +1, 'weight': 0.04,
         'desc': '销售现金含量'},
        {'name': 'asset_turnover_ttm', 'source': 'jqfactor', 'column': 'asset_turnover_ttm', 'direction': +1, 'weight': 0.03,
         'desc': '资产周转率'},
        {'name': 'debt_to_asset_ratio', 'source': 'jqfactor', 'column': 'debt_to_asset_ratio', 'direction': -1, 'weight': 0.03,
         'desc': '低资产负债率'},

        # 流动性结构/风险：与 v1 low_turnover 区分；A股极端情绪/高波通常不友好
        {'name': 'DAVOL20', 'source': 'jqfactor', 'column': 'DAVOL20', 'direction': -1, 'weight': 0.04,
         'desc': '20日/120日换手比，越低越冷静'},
        {'name': 'turnover_volatility', 'source': 'jqfactor', 'column': 'turnover_volatility', 'direction': -1, 'weight': 0.04,
         'desc': '换手率波动，越低越稳'},
        {'name': 'Variance120', 'source': 'jqfactor', 'column': 'Variance120', 'direction': -1, 'weight': 0.04,
         'desc': '120日收益方差，低波'},
        # 2026-08-27 修正：resvol 属 style_pro 线上不支持，换 sharpe_ratio_120（risk 类）
        {'name': 'sharpe_ratio_120', 'source': 'jqfactor', 'column': 'sharpe_ratio_120', 'direction': +1, 'weight': 0.03,
         'desc': '120日夏普，风险调整收益越高越好（替代 resvol）'},

        # 进攻性小开关：52周位置在本地是牛市区制候选，权重很小，避免动量负alpha反噬
        {'name': 'fifty_two_week_close_rank', 'source': 'jqfactor', 'column': 'fifty_two_week_close_rank', 'direction': +1, 'weight': 0.03,
         'desc': '52周价格位置，牛市补偿项'},
    ]

    run_weekly(rebalance, weekday=-1, time='close')
    run_daily(schedule_probe, time='14:29')
    log.info('INIT_OK v2_factor_library N=%d max_ind=%d factors=%d' %
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

    # 3.1) 高股息：finance 分红表手动算（每股分红/股价，替代线上不支持的 divyild）
    div_spec = [s for s in g.FACTOR_SPECS if s['source'] == 'finance']
    if div_spec:
        df['dividend_yield'] = compute_dividend_yield(list(df.index), data_date)
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


def compute_dividend_yield(codes, data_date):
    """用 finance 分红表手动计算股息率（每股分红/股价），替代线上不支持的 divyild。

    取近一年（365 天）内除权除息的现金分红，累计每股分红，除以当前收盘价。
    无分红/取不到 = NaN（打分中性 0.5）。

    2026-08-27 修正记录：
      - STK_DIVIDEND 表不存在（线上实测 'Finance' object has no attribute 'STK_DIVIDEND'）
      - STK_XR_XD 表存在，但字段不是 ex_dividend_date（线上实测 AttributeError）
      - 本版动态探测字段名（xrd_date/ex_dividend_date/dividend_ratio/dividend_per_share），
        并打印 dir() 真值兜底，不再猜。
    """
    result = {}
    import pandas as pd
    try:
        from jqdata import finance
        from datetime import timedelta
        table = finance.STK_XR_XD

        # 关键修正：不要在 query 阶段猜日期字段。
        # 聚宽线上 STK_XR_XD 的 SQLAlchemy 属性名和 run_query 返回列名可能不完全一致；
        # 先只按 code 拉近似样本，再用 DataFrame.columns 识别真实字段，避免 AttributeError。
        q = query(table).filter(table.code.in_(codes))
        div = finance.run_query(q)
        if div is None or len(div) == 0:
            log.warn('DIVIDEND_EMPTY table=STK_XR_XD')
            return pd.Series(result).reindex(codes)

        cols = list(div.columns)
        date_candidates = ['x_date', 'a_xr_date', 'xr_date', 'xrd_date', 'ex_dividend_date',
                           'pay_date', 'plan_announce_date', 'bonus_date', 'report_date',
                           'pub_date', 'pubDate', 'day', 'date', 'statDate', 'end_date']
        div_candidates = ['dividend_ratio', 'dividend_per_share', 'cash_dividend_ratio',
                          'cash_dividend', 'cash_div', 'per_share_dividend']
        date_f = next((f for f in date_candidates if f in cols), None)
        div_f = next((f for f in div_candidates if f in cols), None)
        log.info('STK_XR_XD_DF_COLUMNS=%s' % str(cols))
        log.info('DIVIDEND_FIELDS date_field=%s div_field=%s rows=%d' % (date_f, div_f, len(div)))

        if len(div) > 0:
            try:
                log.info('STK_XR_XD_SAMPLE=%s' % str(div.head(3).to_dict('records'))[:800])
            except Exception:
                pass

        if div_f is None:
            log.warn('DIVIDEND_DIV_FIELD_MISSING columns=%s' % str(cols))
            return pd.Series(result).reindex(codes)

        # 如果日期字段存在，则只取 data_date 前 365 天；若仍识别不到日期字段，
        # 先退化为“最近表内记录的累计分红”并保留日志，避免高股息因子完全中性。
        if date_f is not None:
            div[date_f] = pd.to_datetime(div[date_f], errors='coerce')
            end = pd.to_datetime(data_date)
            start = end - timedelta(days=365)
            div = div[(div[date_f] >= start) & (div[date_f] <= end)]
        else:
            log.warn('DIVIDEND_DATE_FIELD_MISSING_USE_ALL_ROWS columns=%s' % str(cols))

        div = div[pd.to_numeric(div[div_f], errors='coerce') > 0]
        if len(div) > 0:
            for code, grp in div.groupby('code'):
                per_share = pd.to_numeric(grp[div_f], errors='coerce').sum()  # 每股派息（元）
                price = get_price(code, end_date=data_date, count=1, fields=['close'])
                if price is not None and len(price) > 0:
                    px = float(price['close'].iloc[-1])
                    if px and px > 0:
                        result[code] = per_share / px
            return pd.Series(result).reindex(codes)
    except Exception as e:
        log.warn('DIVIDEND_XR_XD_FAILED err=%s' % str(e)[:200])
    return pd.Series(result).reindex(codes)


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
