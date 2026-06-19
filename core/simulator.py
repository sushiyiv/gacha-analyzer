"""蒙特卡洛抽卡模拟模块

基于 core.models.BannerConfig 的精确保底机制模拟，替代遗留的 gacha_engine.py + simulator.py。

=== 模块概述 ===
本模块实现了完整的抽卡（gacha）模拟系统，核心原理是蒙特卡洛方法（Monte Carlo Method）：
通过大量随机重复实验来近似求解概率分布问题。在抽卡场景中，每次"抽卡"本质上是一次
伯努利试验（Bernoulli trial），但概率并非固定不变，而是随着累积抽数（保底计数）的
增加而动态变化（软保底/硬保底机制）。

=== 蒙特卡洛模拟原理 ===
1. 单次模拟：从初始状态出发，模拟一次完整的抽卡过程直到达成目标（如获得限定5星角色）
2. 多次重复：将上述过程重复数千到数万次（如10000次）
3. 统计分析：收集每次模拟所需的抽数，计算均值、中位数、百分位数等统计量
4. 收敛性：根据大数定律，模拟次数越多，统计结果越接近真实概率分布

=== 保底机制说明 ===
- 硬保底（Hard Pity）：达到指定抽数后必定出5星（如90抽必出5星）
- 软保底（Soft Pity）：接近硬保底时，5星概率逐抽递增（如74抽起每抽增加约6%概率）
- 大小保底（50/50）：首次出5星时有50%概率为限定角色；若歪了（未中限定），下次5星必定为限定
"""

# 导入标准库随机数模块，用于生成 [0, 1) 之间的均匀分布随机浮点数
# random.random() 是整个模拟的核心随机源，所有概率判定都依赖此函数
import random

# 导入类型注解：List（列表）、Dict（字典）、Optional（可选值）
# 这些类型注解不会影响运行时行为，仅用于静态类型检查工具（如 mypy）和 IDE 自动补全
from typing import List, Dict, Optional

# 从同级 models 模块导入数据类 BannerConfig 和预定义卡池配置字典 BANNER_CONFIGS
# BannerConfig 是一个 dataclass，包含卡池的所有参数：基础概率、保抽数、限定概率等
from core.models import BannerConfig, BANNER_CONFIGS


class PityState:
    """保底状态追踪（基于 BannerConfig dataclass）

    === 功能说明 ===
    该类维护单次模拟运行中所有与保底相关的状态信息，包括：
    - 当前累积抽数（current_pity）：从上次出5星后累计抽了多少次
    - 是否触发大小保底（is_guaranteed）：上一次5星是否歪了非限定角色
    - 历史记录（pull_history）：记录每次抽卡结果（3星/4星/5星），用于4星保底计算

    === 状态机模型 ===
    每次抽卡（pull_once）会更新内部状态，状态转换关系：
    ┌──────────────┐   出5星    ┌──────────────────┐
    │ 普通状态      │ ────────> │ 保底计数归零      │
    │ (pity 递增)   │           │ 可能触发大保底    │
    └──────────────┘           └──────────────────┘
    """

    def __init__(self, config: BannerConfig, current_pity: int = 0,
                 is_guaranteed: bool = False, epitomized_count: int = 0):
        """初始化保底状态对象

        参数说明：
        - config (BannerConfig): 卡池配置对象，包含该卡池的所有概率参数和保底规则
            结构示例（dataclass）：
            {
                "base_rate_5star": 0.006,        # 5星基础概率（0.6%）
                "soft_pity_start": 74,            # 软保底起始抽数
                "soft_pity_increment": 0.06,      # 软保底每抽概率递增量
                "hard_pity": 90,                  # 硬保底抽数（必出5星）
                "base_rate_4star": 0.051,         # 4星基础概率（5.1%）
                "featured_guarantee_rate": 0.5,   # 限定5星概率（50/50）
                "has_guarantee": True             # 是否有大小保底机制
            }
        - current_pity (int, 默认0): 当前已累积的抽数。模拟器可从任意抽数状态开始
            例如：玩家已抽了70次未出5星，可传入 current_pity=70 继续模拟
        - is_guaranteed (bool, 默认False): 是否处于"大保底"状态
            - True：下次出5星必定是限定角色（上次歪了）
            - False：下次出5星有50/50概率为限定角色
        - epitomized_count (int, 默认0): 命定值计数器（预留字段，当前未使用）
            在某些游戏中，多次歪后系统会直接给予限定角色

        内部机制：
        __init__ 方法仅进行简单的属性赋值，将参数保存为实例变量，供后续方法访问。
        没有复杂的初始化逻辑，因为状态对象的设计理念是"轻量创建、逐步演变"。
        """
        self.config = config                # 存储卡池配置，后续概率计算需要读取其中的参数
        self.current_pity = current_pity    # 当前保底计数器，每次抽卡时 +1，出5星时归零
        self.is_guaranteed = is_guaranteed  # 大保底标志位，控制下次5星是否必定限定
        self.epitomized_count = epitomized_count  # 命定值计数（预留），用于更复杂的保底规则
        # pull_history 用列表存储每次抽卡的星级结果（3/4/5）
        # 列表尾部保留最近9次抽卡结果，用于判断4星保底是否触发
        # 使用 List[int] 类型，元素值为 3/4/5 代表对应星级
        self.pull_history: List[int] = []

    def get_5star_rate(self) -> float:
        """计算当前抽数下的5星概率（核心概率计算函数）

        === 蒙特卡洛模拟中的概率角色 ===
        在蒙特卡洛模拟中，每次抽卡都需要一个概率值来判定是否"中奖"。
        本函数根据当前保底计数动态计算该概率，模拟真实游戏中的概率曲线。

        === 概率计算逻辑（三段式） ===
        ┌─────────────────────────────────────────────────────────┐
        │ 抽数区间          │ 概率计算方式                         │
        ├─────────────────────────────────────────────────────────┤
        │ [0, soft_pity)    │ base_rate_5star（固定基础概率）      │
        │ [soft_pity, hard) │ 基础概率 + 递增量 * (pity - start + 1)│
        │ [hard_pity, ∞)    │ 1.0（100%必出）                     │
        └─────────────────────────────────────────────────────────┘

        === 返回值说明 ===
        返回 float 类型的概率值，范围 [0.0, 1.0]。
        返回值用于 random.random() < rate 判定是否出5星。

        参数：无（使用实例变量 self.current_pity 和 self.config）
        """
        # 硬保底判定：当累积抽数 >= 硬保底抽数时，概率直接设为 1.0（100%出5星）
        # 这是游戏的最高保底机制，确保玩家不会无限歪下去
        if self.current_pity >= self.config.hard_pity:
            return 1.0

        # 软保底判定：当累积抽数 >= 软保底起始抽数但未到硬保底时
        # 概率开始逐抽递增，形成"概率爬坡"效果
        if self.current_pity >= self.config.soft_pity_start:
            # 计算软保底额外概率：(当前抽数 - 软保底起始 + 1) * 每抽递增量
            # +1 的原因：在 soft_pity_start 这一抽就应获得第一次递增
            # 例如：soft_pity_start=74, soft_pity_increment=0.06
            #   第74抽：extra = (74-74+1) * 0.06 = 0.06
            #   第75抽：extra = (75-74+1) * 0.06 = 0.12
            #   ...
            #   第89抽：extra = (89-74+1) * 0.06 = 0.96
            extra = (self.current_pity - self.config.soft_pity_start + 1) * self.config.soft_pity_increment
            # 使用 min() 确保最终概率不超过 1.0
            # 因为递增量叠加基础概率可能超过 100%（虽然在合理参数下不太可能发生）
            return min(self.config.base_rate_5star + extra, 1.0)

        # 普通阶段：未达到软保底起始抽数时，使用固定的基础5星概率
        # 这是玩家大部分抽卡时间里的概率状态
        return self.config.base_rate_5star

    def pull_once(self):
        """执行一次抽卡，返回 (是否出5星, 是否限定5星, 是否出4星)

        === 蒙特卡洛单次试验 ===
        这是蒙特卡洛模拟中最基本的"一次试验"。每次调用相当于玩家在游戏中点击一次"抽卡"按钮。
        内部通过 random.random() 生成 [0, 1) 的均匀分布随机数，与概率阈值比较来决定结果。

        === 抽卡判定顺序（优先级从高到低） ===
        1. 先判定是否出5星（概率最高优先级，保底机制生效）
        2. 若未出5星，再判定是否出4星
        3. 都未中，则为3星（保底结果）

        === 返回值结构 ===
        返回一个三元组 (tuple)：
        - is_5star (bool): 本次是否抽到5星
        - is_featured (bool): 若出5星，是否为限定角色（若未出5星则为 False）
        - is_4star (bool): 本次是否抽到4星（5星和4星互斥，不可能同时出现）

        === 状态副作用 ===
        该方法会修改以下实例状态：
        - self.current_pity: 抽卡时 +1，出5星时归零
        - self.is_guaranteed: 可能被 _resolve_featured() 修改（歪了则置 True）
        - self.pull_history: 追加本次抽卡结果（3/4/5）
        """
        # 保底计数器 +1，表示又多抽了一次
        # 这个计数器是软保底和硬保底的基础，决定了当前的概率
        self.current_pity += 1

        # 计算当前抽数对应的5星概率
        # get_5star_rate() 会根据 current_pity 的值动态返回不同概率
        rate = self.get_5star_rate()

        # === 5星判定 ===
        # random.random() 返回 [0.0, 1.0) 的均匀分布随机数
        # 若随机数 < rate，则判定为"中奖"（出5星）
        # 这是标准的"反变换采样"（Inverse Transform Sampling）的简化形式
        # 数学上：P(X <= rate) = rate，因此判定 random() < rate 等价于以 rate 概率中奖
        if random.random() < rate:
            # 出5星后，保底计数器归零，重新开始计数
            self.current_pity = 0
            # 决定本次出的5星是否为限定角色（涉及大小保底机制）
            is_featured = self._resolve_featured()
            # 将5星结果记入历史记录（值为5）
            self.pull_history.append(5)
            # 返回三元组：出5星=True, 是否限定=is_featured, 是否4星=False（不可能同时出5星和4星）
            return True, is_featured, False

        # === 4星判定 ===
        # 只有在未出5星的前提下才会检查4星概率
        # _check_4star() 会结合4星保底机制和基础概率来判定
        if self._check_4star():
            # 将4星结果记入历史记录（值为4）
            self.pull_history.append(4)
            # 返回三元组：出5星=False, 是否限定=False（未出5星无所谓限定）, 是否4星=True
            return False, False, True

        # === 3星保底 ===
        # 既未中5星也未中4星，结果为3星（最普通的产物）
        # 3星没有任何特殊效果，仅记录在历史中用于4星保底判定
        self.pull_history.append(3)
        # 返回三元组：全部为 False，表示本次抽卡没有任何高星产物
        return False, False, False

    def _resolve_featured(self) -> bool:
        """决定出的5星是否为限定角色（大小保底机制判定）

        === 大小保底机制原理 ===
        在很多抽卡游戏中，5星角色分为"限定角色"和"常驻角色"。
        大小保底机制确保玩家不会连续歪（获得非限定角色）：
        - 第一次出5星：有 featured_guarantee_rate（通常50%）概率为限定角色
        - 若歪了（未中限定）：下次出5星必定为限定角色（is_guaranteed = True）
        - 若中了限定：下次出5星重新进入50/50判定

        === 状态转换图 ===
        ┌──────────────────┐  50/50赢  ┌──────────────────┐
        │ 小保底（正常）    │ ────────> │ 中限定，重置状态  │
        │ is_guaranteed=F  │           │ is_guaranteed=F  │
        └──────────────────┘           └──────────────────┘
               │ 50/50输                         ↑
               ▼                                  │
        ┌──────────────────┐  大保底必定限定  ┌──────┘
        │ 歪了，进入大保底  │ ────────────> │
        │ is_guaranteed=T  │               │
        └──────────────────┘               │

        === 返回值说明 ===
        返回 bool：True 表示本次5星是限定角色，False 表示是常驻角色（歪了）

        参数：无（使用实例变量）
        """
        # 获取卡池配置中的限定概率参数
        config = self.config

        # 检查该卡池是否支持大小保底机制
        # 有些卡池（如武器池或特殊卡池）可能没有大小保底
        # 如果没有大小保底机制，每次出5星都是随机的，不受上次结果影响
        if not config.has_guarantee:
            return False

        # === 大保底触发判定 ===
        # 如果 is_guaranteed 为 True，说明上次5星歪了（非限定）
        # 根据大小保底机制，本次出的5星必定是限定角色
        if self.is_guaranteed:
            # 重置大保底标志位，因为本次已经享受了大保底的必定限定
            self.is_guaranteed = False
            # 大保底触发，必定返回 True（限定角色）
            return True

        # === 50/50 判定 ===
        # 当前处于小保底状态（上次未歪或从未歪过）
        # 以 featured_guarantee_rate（通常0.5）的概率判定是否为限定角色
        if random.random() < config.featured_guarantee_rate:
            # 50/50 赢了，本次是限定角色
            # is_guaranteed 保持 False，下次出5星仍为50/50判定
            return True
        else:
            # 50/50 输了，本次不是限定角色（歪了）
            # 设置 is_guaranteed = True，标记下次出5星必定为限定
            self.is_guaranteed = True
            # 返回 False 表示本次歪了
            return False

    def _check_4star(self) -> bool:
        """检查4星保底是否触发（简化处理版本）

        === 4星保底机制 ===
        与5星保底类似，4星也有保底机制：
        - 基础概率：每次抽卡有 base_rate_4star（约5.1%）概率出4星
        - 保底触发：连续10抽未出4星或以上（4星+），第10抽必定出4星

        === 简化处理说明 ===
        本实现简化了4星保底的细节（如4星中也有大小保底机制），
        仅保留了核心的"10抽保底"和基础概率判定，因为：
        1. 4星对模拟结果（5星相关统计）影响较小
        2. 简化后不影响5星概率曲线的准确性
        3. 降低模拟计算量

        === 返回值说明 ===
        返回 bool：True 表示本次抽到4星，False 表示未出4星

        参数：无（使用实例变量）
        """
        # 计算最近9次抽卡中4星及以上（4星和5星）的数量
        # pull_history[-9:] 取最近9次记录（如果历史不足9次则取全部）
        # sum(1 for p in ...) 统计满足 p >= 4 的记录数（即4星和5星的总数）
        # 使用 >= 4 而不是 == 4 是因为5星也包含在内（4星和5星都算"高星"）
        pity_4star = sum(1 for p in self.pull_history[-9:] if p >= 4)

        # 4星保底判定：
        # 条件1：最近9次中没有任何4星或5星（pity_4star == 0）
        # 条件2：总抽数 >= 10（确保有足够的历史记录来判定保底）
        # 当两个条件都满足时，说明已经连续9抽未出4星+，第10抽必定出4星
        if pity_4star == 0 and len(self.pull_history) >= 10:
            return True

        # 如果未触发4星保底，则以 base_rate_4star（约5.1%）的基础概率随机判定
        # 同样使用 random.random() < rate 的标准概率判定方式
        return random.random() < self.config.base_rate_4star


def simulate_pulls(config: BannerConfig, num_pulls: int,
                   current_pity: int = 0, is_guaranteed: bool = False):
    """模拟N次抽卡，返回详细结果

    === 函数功能 ===
    从指定的初始状态（当前保底计数和大小保底状态）出发，模拟连续抽卡 num_pulls 次，
    收集并返回详细的抽卡统计数据。这是单次完整模拟的执行函数。

    === 蒙特卡洛框架中的角色 ===
    在蒙特卡洛模拟中，该函数执行"一次完整实验"（一个样本路径）。
    通过多次调用该函数（或在其内部循环中多次实验），
    可以得到抽数的分布，进而计算各种统计指标。

    === 参数数据结构 ===
    - config (BannerConfig): 卡池配置对象，传递给 PityState 用于概率计算
    - num_pulls (int): 本次模拟的总抽卡次数，必须 >= 0
        - 若为 0：返回空结果，不执行任何抽卡
        - 若为负数：range() 不会迭代，同样返回空结果
    - current_pity (int, 默认0): 初始保底计数，允许模拟中途状态
    - is_guaranteed (bool, 默认False): 初始大小保底状态

    === 返回值数据结构 ===
    返回一个二元组 (results_dict, state_object)：
    - results (Dict): 包含以下键值对：
        - "total_pulls" (int): 总抽卡次数
        - "five_stars" (List[Dict]): 每个5星的详细信息列表
            每个元素包含：
            - "pull" (int): 第几抽出的5星（1-indexed）
            - "is_featured" (bool): 是否为限定角色
            - "pity_count" (int): 距离上次5星的抽数（保底计数）
        - "four_stars" (int): 4星总数量
        - "featured_count" (int): 限定5星总数
        - "off_featured_count" (int): 非限定5星（歪的）总数
        - "pulls_per_5star" (List[int]): 每个5星之间的抽数间隔列表
    - state (PityState): 模拟结束后的保底状态对象
        调用方可以读取此状态继续模拟（实现连续模拟）

    === 异常处理 ===
    本函数不会主动抛出异常，但以下情况需要注意：
    - num_pulls < 0 时：range(num_pulls) 不迭代，返回空结果（非异常）
    - config 参数无效时：会沿用 BannerConfig 的验证逻辑（在 models 层处理）
    """
    # 创建保底状态对象，初始化为指定的起始状态
    # PityState 内部维护当前保底计数和大小保底标志
    state = PityState(config, current_pity, is_guaranteed)

    # 初始化结果字典，预分配所有必要的键
    # 使用字典而非自定义类是为了方便序列化为 JSON（用于前端展示）
    results = {
        "total_pulls": num_pulls,    # 记录本次模拟的总抽卡次数
        "five_stars": [],            # 列表，存储每个5星的详细信息字典
        "four_stars": 0,             # 计数器，累计4星数量
        "featured_count": 0,         # 计数器，累计限定5星数量
        "off_featured_count": 0,     # 计数器，累计非限定5星（歪了）数量
        "pulls_per_5star": [],       # 列表，存储相邻5星之间的抽数间隔
    }

    # last_5star_pull 记录上一次出5星是第几抽
    # 初始化为0，表示"尚未出过5星"
    # 用于计算每个5星之间的抽数间隔（pulls_per_5star）
    last_5star_pull = 0

    # 主循环：逐抽执行模拟
    # range(num_pulls) 生成 [0, 1, 2, ..., num_pulls-1] 的迭代器
    # 每次迭代代表一次抽卡（i 从0开始，实际抽数为 i+1）
    for i in range(num_pulls):
        # 执行一次抽卡，获取三个布尔值结果
        # state.pull_once() 会自动更新内部保底状态
        is_5star, is_featured, is_4star = state.pull_once()

        # === 5星处理 ===
        if is_5star:
            # 计算本次抽卡的序号（1-indexed，即第1抽、第2抽...）
            pull_num = i + 1

            # 在 five_stars 列表中追加本次5星的详细信息
            # 使用字典结构存储，方便后续分析和前端展示
            results["five_stars"].append({
                "pull": pull_num,                          # 第几抽出的5星
                "is_featured": is_featured,                # 是否为限定角色
                "pity_count": pull_num - last_5star_pull,  # 距离上次5星的抽数（本次保底计数）
            })

            # 记录相邻5星之间的抽数间隔
            # 例如：第50抽和第120抽各出一个5星，则间隔为 120-50=70
            # 这个数据用于分析"平均多少抽出一个5星"
            results["pulls_per_5star"].append(pull_num - last_5star_pull)

            # 根据是否为限定角色，分别更新对应的计数器
            if is_featured:
                results["featured_count"] += 1    # 限定5星计数 +1
            else:
                results["off_featured_count"] += 1  # 非限定5星计数 +1

            # 更新 last_5star_pull 为本次抽数，供下次5星计算间隔使用
            last_5star_pull = pull_num

        # === 4星处理 ===
        elif is_4star:
            # 4星只需计数，不需要记录详细信息（因为4星对主要分析目标影响较小）
            results["four_stars"] += 1

    # 返回二元组：(结果字典, 最终保底状态)
    # state 对象包含模拟结束后的保底状态，可用于继续模拟或分析
    return results, state


def pulls_until_featured(config: BannerConfig, current_pity: int = 0,
                         is_guaranteed: bool = False, max_pulls: int = 1000) -> int:
    """模拟抽到限定5星需要多少抽

    === 函数功能 ===
    从指定初始状态出发，模拟抽卡直到获得第一个限定5星角色，返回所需抽数。
    这是蒙特卡洛模拟中最基本的"单次实验"单元。

    === 在蒙特卡洛框架中的角色 ===
    monte_carlo_simulate() 函数会多次调用本函数，每次调用产生一个样本点。
    所有样本点的集合构成抽数的统计分布。

    === 参数说明 ===
    - config (BannerConfig): 卡池配置对象
    - current_pity (int, 默认0): 初始保底计数（已抽次数）
    - is_guaranteed (bool, 默认False): 初始大小保底状态
    - max_pulls (int, 默认1000): 最大抽卡次数上限
        - 防止极端情况下模拟无限循环
        - 1000抽已远超任何游戏的保底上限，实际几乎不可能触发
        - 若达到上限仍未出限定，返回 max_pulls 作为兜底值

    === 返回值说明 ===
    返回 int：抽到限定5星所需的抽卡次数
        - 正常情况：返回 [1, max_pulls] 之间的值
        - 极端情况：返回 max_pulls（意味着在 max_pulls 次内未出限定5星）

    === 异常处理 ===
    - max_pulls <= 0 时：range 不迭代，直接返回 max_pulls
    - 无大小保底的卡池（has_guarantee=False）：_resolve_featured() 始终返回 False，
      导致模拟永远无法获得"限定"角色，最终返回 max_pulls
    """
    # 创建保底状态对象
    state = PityState(config, current_pity, is_guaranteed)

    # 主循环：从第1抽开始，最多抽 max_pulls 次
    # range(1, max_pulls + 1) 生成 [1, 2, ..., max_pulls] 的迭代器
    # 使用 1-indexed 是因为返回值表示"第几抽"，与用户直觉一致
    for i in range(1, max_pulls + 1):
        # 执行一次抽卡
        # is_5star: 是否出5星
        # is_featured: 是否为限定角色
        # _ : 4星标志被忽略（使用下划线占位），因为本函数只关心限定5星
        is_5star, is_featured, _ = state.pull_once()

        # 同时满足"出5星"和"是限定角色"时，模拟成功
        # 这是本函数的终止条件
        if is_5star and is_featured:
            return i  # 返回当前抽数（1-indexed）

    # 达到最大抽卡次数仍未获得限定5星
    # 返回 max_pulls 作为兜底值，表示"在上限内未达成目标"
    # 在实际应用中，由于保底机制的存在，这种情况极其罕见
    return max_pulls


def monte_carlo_simulate(config: BannerConfig, current_pity: int = 0,
                         is_guaranteed: bool = False, target_featured: int = 1,
                         simulations: int = 10000) -> List[int]:
    """Monte Carlo 模拟抽到目标数量限定5星需要的抽数

    === 蒙特卡洛模拟核心函数 ===
    本函数实现了标准的蒙特卡洛方法流程：
    1. 重复 simulations 次（默认10000次）独立实验
    2. 每次实验模拟获得 target_featured 个限定5星所需的总抽数
    3. 收集所有实验结果，返回抽数列表

    === 数学原理 ===
    设 X_i 为第 i 次实验中获得目标限定5星所需的抽数，
    则 {X_1, X_2, ..., X_N} 是独立同分布（i.i.d.）的随机变量样本。
    根据大数定律，当 N 足够大时，样本均值 E[X] ≈ (1/N) * ΣX_i
    样本分布趋近于真实分布。

    === 参数数据结构 ===
    - config (BannerConfig): 卡池配置对象
    - current_pity (int, 默认0): 初始保底计数
    - is_guaranteed (bool, 默认False): 初始大小保底状态
    - target_featured (int, 默认1): 目标限定5星数量
        - 1：模拟抽取1个限定5星
        - N：模拟抽取N个限定5星（如模拟满命需要的抽数）
    - simulations (int, 默认10000): 模拟实验次数
        - 越大结果越精确，但计算时间越长
        - 10000次通常足够得到稳定的统计结果
        - 建议范围：1000~100000

    === 返回值数据结构 ===
    返回 List[int]：长度为 simulations 的整数列表
        每个元素代表一次独立实验中获得 target_featured 个限定5星的总抽数
        例如：[72, 156, 89, 201, ...]

    === 异常处理 ===
    - simulations <= 0 时：不执行循环，返回空列表 []
    - target_featured <= 0 时：while 条件立即为 False，total_pulls=0，返回全零列表
    - max_pulls 上限由 pulls_until_featured 内部控制（默认1000）
    """
    # 初始化结果列表，用于收集每次模拟实验的总抽数
    results = []

    # 主循环：执行 simulations 次独立实验
    # 每次迭代是一个完全独立的模拟实验，模拟获得 target_featured 个限定5星的完整过程
    for _ in range(simulations):
        # total_pulls 累计本次实验中所有抽卡次数
        # 每次实验开始时重置为0
        total_pulls = 0

        # featured_count 记录本次实验中已获得的限定5星数量
        # 每次实验开始时重置为0
        featured_count = 0

        # state_pity 和 state_guaranteed 跟踪本次实验中的保底状态
        # 初始值来自函数参数（允许模拟从任意状态开始）
        # 注意：这里的命名加了 state_ 前缀，避免与函数参数混淆
        state_pity = current_pity
        state_guaranteed = is_guaranteed

        # 内循环：持续抽卡直到获得 target_featured 个限定5星
        # 每次迭代调用 pulls_until_featured() 获得一个限定5星，
        # 然后更新保底状态，继续下一轮
        while featured_count < target_featured:
            # 调用 pulls_until_featured() 模拟获得一个限定5星所需的抽数
            # 使用当前的保底状态（state_pity, state_guaranteed）
            pulls = pulls_until_featured(config, state_pity, state_guaranteed)

            # 累加本次获得限定5星所用的抽数
            total_pulls += pulls

            # 已获得的限定5星数量 +1
            featured_count += 1

            # 出完限定5星后，保底状态重置：
            # - state_pity = 0：新一个5星周期从0开始计数
            # - state_guaranteed = False：大保底已使用，重置为小保底状态
            state_pity = 0
            state_guaranteed = False

        # 本次实验完成，将总抽数加入结果列表
        results.append(total_pulls)

    # 返回所有实验的抽数列表，供后续统计分析使用
    return results


def analyze_simulation_results(results: List[int], target_featured: int = 1) -> Dict:
    """分析模拟结果，计算各种统计指标

    === 函数功能 ===
    对蒙特卡洛模拟返回的抽数列表进行统计分析，计算：
    1. 基本统计量（均值、中位数、最小值、最大值）
    2. 各抽数阈值的累积概率分布（CDF）
    3. 百分位数分布（欧皇/非酋分级）

    === 参数数据结构 ===
    - results (List[int]): 蒙特卡洛模拟返回的抽数列表
        每个元素是一次完整实验中获得目标限定5星所需的总抽数
        例如：[72, 156, 89, 201, ...]，长度等于 simulations 参数值
    - target_featured (int, 默认1): 目标限定5星数量（用于标签显示）

    === 返回值数据结构 ===
    返回 Dict，包含以下键值对：
    - "simulations" (int): 模拟总次数（即结果列表长度）
    - "target_featured" (int): 目标限定5星数量
    - "average" (float): 平均所需抽数（四舍五入到2位小数）
    - "median" (int): 中位数抽数（50%概率在此抽数内获得目标）
    - "min" (int): 最少所需抽数（最幸运的情况）
    - "max" (int): 最多所需抽数（最不幸的情况）
    - "prob_table" (Dict[int, float]): 各抽数阈值的累积概率
        键为抽数阈值，值为"在该抽数内获得目标"的概率
    - "percentiles" (Dict[str, int]): 百分位数分级
        以中文标签标注不同运气等级对应的抽数
    - "raw_results" (List[int]): 原始抽数列表（保留完整数据供后续使用）

    === 统计学说明 ===
    - 中位数（Median）：将数据排序后位于中间的值，比均值更抗异常值干扰
    - 百分位数（Percentile）：P% 的数据小于等于该值
    - 累积概率（CDF）：P(X <= t) 的经验估计，即 count(r <= t) / n
    """
    # 对抽数列表进行升序排序
    # 排序后可以方便地计算中位数、百分位数等分位数统计量
    results_sorted = sorted(results)

    # 获取结果列表的长度（即模拟次数 n）
    n = len(results_sorted)

    # === 基本统计量计算 ===

    # 平均值：所有抽数之和除以模拟次数
    # 这是蒙特卡洛估计的期望值 E[X] 的样本近似
    avg = sum(results) / n

    # 中位数：排序后第 n//2 个元素
    # Python 整数除法 // 确保索引为整数
    # 当 n 为偶数时取中间偏右的值（偶数情况的中位数通常取两个中间值的平均，
    # 但这里简化为取一个值，对大量数据误差可忽略）
    median = results_sorted[n // 2]

    # 最小值：排序后第一个元素（最少抽数，最幸运的情况）
    min_val = results_sorted[0]

    # 最大值：排序后最后一个元素（最多抽数，最不幸的情况）
    max_val = results_sorted[-1]

    # === 累积概率分布（CDF）计算 ===
    # 定义一组抽数阈值，用于计算"在该抽数内获得目标"的概率
    # 这些阈值覆盖了从10抽到200抽的范围，对应不同的运气等级
    thresholds = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 180, 200]
    prob_table = {}

    # 遍历每个阈值，计算累积概率
    for t in thresholds:
        # 统计抽数 <= t 的实验次数
        # 使用生成器表达式和 sum(1 for ...) 进行计数
        # 这是对经验累积分布函数 F(t) = P(X <= t) 的近似
        count = sum(1 for r in results if r <= t)

        # 计算概率：符合条件的次数 / 总模拟次数
        # 当 simulations 足够大时，该值趋近于真实概率
        prob_table[t] = count / n

    # === 百分位数分布（欧皇/非酋分级） ===
    # 用中文标签标注不同运气等级对应的抽数
    # 这些标签让结果对中文用户更友好
    percentiles = {
        # 前10%：最幸运的10%玩家需要的抽数（少于等于该抽数）
        # 即有10%的概率在这个抽数内获得目标
        "欧皇 (前10%)": results_sorted[int(n * 0.1)],

        # 前25%：较幸运的25%玩家
        "偏欧 (前25%)": results_sorted[int(n * 0.25)],

        # 50%：中位数，一半玩家在此抽数内获得目标
        "正常 (50%)": median,

        # 前75%：较不幸的玩家（需要更多抽数）
        "偏非 (前75%)": results_sorted[int(n * 0.75)],

        # 前90%：不幸的玩家
        "非酋 (前90%)": results_sorted[int(n * 0.9)],

        # 前99%：极其不幸的玩家（几乎是最坏情况）
        "究极非酋 (前99%)": results_sorted[int(n * 0.99)],
    }

    # 返回完整的分析结果字典
    # 所有统计指标打包在一个字典中，方便前端直接使用
    return {
        "simulations": n,                  # 模拟总次数
        "target_featured": target_featured, # 目标限定5星数量
        "average": round(avg, 2),           # 平均抽数（保留2位小数）
        "median": median,                   # 中位数抽数
        "min": min_val,                     # 最少抽数
        "max": max_val,                     # 最多抽数
        "prob_table": prob_table,           # 各阈值的累积概率
        "percentiles": percentiles,         # 百分位数分级
        "raw_results": results,             # 原始抽数列表（完整数据）
    }
