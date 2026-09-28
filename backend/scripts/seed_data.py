# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 种子数据初始化

灌入三类种子数据：
  1. species  —— 23 类物种（形态/习性/分布文案由人工撰写，非模型生成）
  2. system_config —— 5 项运行期配置
  3. 管理员账号 —— 1 个

幂等：重复运行不产生重复行（按唯一键先查后写）。

【重要】species 的 23 条文案是本项目**唯一的知识库来源**。
fish_18 官方仅到科级（Scaridae 鹦嘴鱼科），文案【必须按科级描述】，
不得杜撰种名 —— 详见 docs/海瞳鱼鉴-PRD.md 与 ml/dataset/species_meta.py。
"""

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
_ROOT = os.path.dirname(_BACKEND)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sqlalchemy import select          # noqa: E402

from app.core.database import Base, engine   # noqa: E402
from app.models import SpeciesModel, SystemConfig, User  # noqa: E402
from app.services.user_service import ensure_admin        # noqa: E402

sys.path.insert(0, os.path.join(_ROOT, 'ml'))
from dataset.species_meta import SPECIES   # noqa: E402

# ---------------- 23 类物种知识库 ----------------
# 键为 class_index（0 基）。中文名与拉丁名由 species_meta.py 提供，此处只补文案。

SPECIES_TEXT: dict[int, dict] = {
    0: dict(family='雀鲷科 Pomacentridae',
            morphology='体呈卵圆形而侧扁，全长约 6～8 cm。体色灰褐，鳞片边缘色深，'
                       '形成明显的网状格纹，这也是中文名的由来。吻短，口小，'
                       '背鳍前部硬棘 12 枚。尾柄与尾鳍浅灰，无明显暗斑。',
            habit='珊瑚礁区常见小型鱼类，常成群停留在分枝珊瑚上方数厘米处，'
                  '受惊时迅速钻入珊瑚枝隙。以浮游动物为主食，兼食藻类。'
                  '繁殖期雄鱼在礁石上清理产卵床并护卵。',
            distribution='印度—西太平洋：东非至萨摩亚，北达琉球群岛，'
                         '南至大堡礁；中国台湾、海南岛及南海诸岛珊瑚礁海域常见。'),
    1: dict(family='雀鲷科 Pomacentridae',
            morphology='体呈椭圆形，全长约 7 cm。体色深褐至近黑，'
                       '体侧具一条自背鳍前方延伸至胸部的白色横带为其标志特征。'
                       '背鳍硬棘 12 枚，软条 15～16 枚。尾鳍浅凹。',
            habit='栖息于珊瑚礁外缘与礁池，单独或成对活动，'
                  '领域性强，会驱赶侵入其觅食区的同类。以丝状藻类为主要食物。',
            distribution='印度—西太平洋热带海域，自斯里兰卡至社会群岛；'
                         '中国南海与台湾沿海珊瑚礁有分布。'),
    2: dict(family='雀鲷科 Pomacentridae',
            morphology='体延长而侧扁，全长可达 10 cm。体色银白至淡蓝，'
                       '尾鳍呈鲜明的黄色或橙黄色，为其显著特征。'
                       '背鳍硬棘 13 枚。吻部短钝，眼较大。',
            habit='群游性极强，常成数十至数百尾的大群在水层中上层活动，'
                  '靠群体数量规避捕食者。以浮游动物为食。繁殖期有护卵行为。',
            distribution='西太平洋：日本南部至澳大利亚北部，'
                         '包括中国台湾、菲律宾与南海诸岛海域。'),
    3: dict(family='雀鲷科 Pomacentridae',
            morphology='体侧扁呈椭圆形，全长约 8～10 cm。体色变异较大，'
                       '常见为体侧具 2～3 条白色垂直宽带，底色由橙褐至深褐不等。'
                       '各鳍边缘多具黑白相间的边。',
            habit='与海葵共生，是其最典型的生态习性——体表黏液使其免于海葵刺细胞伤害，'
                  '借海葵触手获得庇护，同时为海葵清除寄生虫与残饵。'
                  '杂食，以藻类与小型无脊椎动物为食。为雌雄同体，可顺序性逆转。',
            distribution='印度—西太平洋：波斯湾至萨摩亚，'
                         '北至日本南部；中国台湾、海南与南海珊瑚礁区常见。'),
    4: dict(family='蝴蝶鱼科 Chaetodontidae',
            morphology='体呈圆形而甚侧扁，全长约 12～15 cm。'
                       '体侧具多条呈新月形弯曲的暗色横纹，为本种最显著的识别特征。'
                       '吻短，口小；背鳍硬棘 13～14 枚。',
            habit='成对或小群活动于珊瑚繁茂的礁区，日行性。'
                  '以珊瑚虫、小型无脊椎动物与藻类为食，'
                  '常以尖吻啄食珊瑚枝间的猎物。夜间藏于礁隙休息。',
            distribution='西太平洋至中太平洋，自琉球群岛、菲律宾至夏威夷；'
                         '中国台湾与南海珊瑚礁海域有分布。'),
    5: dict(family='蝴蝶鱼科 Chaetodontidae',
            morphology='体侧扁呈椭圆形，全长约 15 cm。体侧具三条黑色垂直宽带，'
                       '带间为白色或淡黄色，形成鲜明的川字形纹样，'
                       '中文名即由此而来。背鳍与臀鳍具黑色边缘。',
            habit='栖息于分枝珊瑚（尤以鹿角珊瑚）茂密处，'
                  '因体型侧扁可在珊瑚枝间灵活穿行。'
                  '以珊瑚虫为主要食物，食性专一，对珊瑚退化敏感，'
                  '是珊瑚礁健康度的指示种之一。',
            distribution='印度—西太平洋：红海与东非至印度尼西亚、'
                         '大堡礁与日本南部；中国南海有分布。'),
    6: dict(family='金鳞鱼科 Holocentridae',
            morphology='体呈椭圆形，全长约 18～20 cm。体色银白微带粉红，'
                       '各鳞片具深色边缘。第一背鳍硬棘与臀鳍硬棘具毒腺。'
                       '眼大，为其夜行性生活提供良好暗视觉。',
            habit='夜行性，白天成群隐蔽于礁穴、礁檐阴影处，'
                  '入夜后游出礁区觅食浮游甲壳类与小鱼。受惊时以硬棘防御。',
            distribution='印度—太平洋：东非至夏威夷与马克萨斯群岛；'
                         '中国台湾与南海诸岛珊瑚礁区有分布。'),
    7: dict(family='刺尾鱼科 Acanthruidae',
            morphology='体呈椭圆形而侧扁，全长约 18～21 cm。'
                       '体色深褐至黑褐，体侧密布细密横纹。'
                       '尾柄两侧各具一枚尖锐的白色骨质棘，为其防御器官。'
                       '尾鳍呈弯月形。',
            habit='栖息于礁坡与礁缘水流较强处，单独或小群活动。'
                  '以礁面附着的丝状藻类为食，用梳状齿刮取。'
                  '受威胁时以尾柄棘抽击，可造成深切割伤。',
            distribution='印度—太平洋：红海与东非至日本、'
                         '大堡礁与夏威夷；中国台湾与南海有分布。'),
    8: dict(family='隆头鱼科 Labridae',
            morphology='体延长而侧扁，全长可达 25 cm。'
                       '成鱼体侧具 5～6 条明显的黑色垂直宽带，带间体色灰绿。'
                       '幼鱼体色与成鱼差异较大，为淡褐色带白斑。'
                       '唇厚而突出，上下颌各具两列锥形齿。',
            habit='栖息于砂泥底与礁石混合区，常单独缓慢巡游，'
                  '以翻搅沙底的方式捕食底栖无脊椎动物（多毛类、甲壳类）。'
                  '体色随生长阶段与性别变化显著，属雌雄同体先雌后雄型的典型。',
            distribution='印度—太平洋：红海与东非至社会群岛，'
                         '北至日本南部；中国台湾、海南与南海有分布。'),
    9: dict(family='金鳞鱼科 Holocentridae',
            morphology='体呈椭圆形，全长约 15～18 cm。体色银红，'
                       '体侧散布不规则暗红色斑。'
                       '各鳍鳍条间具明显白斑或白线，为其显著特征。'
                       '下颌略突出，吻端具短须状结构。',
            habit='夜行性，昼间集群隐藏于礁穴与礁檐下，'
                  '日落后分散至藻床与砂底觅食。以底栖甲壳类与小型鱼类为食。'
                  '受惊时迅速以硬棘支撑身体卡入礁隙。',
            distribution='印度—太平洋：东非与红海至夏威夷、'
                         '马绍尔群岛；中国台湾与南海珊瑚礁区有分布。'),
    10: dict(family='雀鲷科 Pomacentridae',
            morphology='体呈卵圆形而侧扁，全长约 14～17 cm。'
                       '体色灰蓝，体侧具 5 条深蓝色垂直宽横带，'
                       '条带间为较浅的底色，故名五带豆娘鱼。'
                       '背鳍硬棘 13 枚，尾鳍深凹。',
            habit='群游性，常成数十尾的大群在礁区中上层活动，'
                  '是礁区最常见的背景鱼之一。杂食性，'
                  '以浮游生物、藻类与底栖小动物为食。繁殖期雄鱼筑巢护卵。',
            distribution='印度—西太平洋：红海与东非至日本南部、'
                         '澳大利亚与新喀里多尼亚；中国南海与台湾沿岸常见。'),
    11: dict(family='单棘鲀科 Monacanthidae',
            morphology='体呈卵圆形而侧扁，全长约 10～11 cm。'
                       '体侧具多条暗褐色斜向宽带，带间为白色细点或细线。'
                       '吻部略突出，眼上方具一根可竖立的短棘。'
                       '腹部无骨盆鳍，仅有一片可活动的皮褶。',
            habit='栖息于珊瑚礁与藻床，单独或成对活动，行动缓慢。'
                  '以珊瑚、柳珊瑚、藻类与海绵等为食。'
                  '受惊时以吻部与腹部皮褶配合膨胀身体卡入礁隙。',
            distribution='印度—太平洋：东非至萨摩亚、日本南部与'
                         '澳大利亚北部；中国台湾与南海有分布。'),
    12: dict(family='雀鲷科 Pomacentridae',
            morphology='体侧扁呈椭圆形，全长约 6～7 cm。'
                       '体色橙黄至橙褐，各鳞片具深色边缘；'
                       '背鳍后部与臀鳍具黑色斑块。'
                       '属小型雀鲷，是珊瑚礁中体型最小的鱼类之一。',
            habit='领域性极强，常固守一小片分枝珊瑚或礁石缝隙，'
                  '驱赶体型更大的入侵者。以藻类与浮游生物为食。'
                  '因体型小且色艳，是礁区观赏性鱼类之一。',
            distribution='西太平洋热带海域：印度尼西亚、菲律宾、'
                         '中国台湾与南海诸岛；大堡礁北部有分布。'),
    13: dict(family='刺尾鱼科 Acanthruidae',
            morphology='体呈卵圆形而甚侧扁，全长约 18～20 cm。'
                       '体色深褐至近黑，体侧散布细小暗色点。'
                       '吻部较长，口小；尾柄两侧各具一枚骨质锐棘。'
                       '受惊时体色可略为变浅，并展开各鳍。',
            habit='栖息于礁坡与礁池，单独或成小群活动。'
                  '以礁面与石面附着的藻类为食，用齿刮取。'
                  '幼鱼与成鱼栖息深度差异明显，幼鱼偏好浅水礁池。',
            distribution='印度—太平洋：红海与东非至日本、'
                         '大堡礁与马绍尔群岛；中国南海有分布。'),
    14: dict(family='隆头鱼科 Labridae',
            morphology='体延长而侧扁，全长可达 30 cm，是本属体型较大者。'
                       '成鱼体色深褐，头部与背鳍前部色更深；'
                       '体侧无明显横带，但头部具数条暗色斜纹。'
                       '唇厚，下颌具向前突出的犬齿状齿。',
            habit='栖息于砂石混合底质，单独活动，'
                  '以翻转石块与翻搅砂底的方式捕食底栖无脊椎动物。'
                  '个体发育中体色与性别变化显著，雄鱼体型通常大于雌鱼。',
            distribution='印度—太平洋：红海与东非至日本南部、'
                         '大堡礁与新喀里多尼亚；中国台湾与南海有分布。'),
    15: dict(family='笛鲷科 Lutjanidae',
            morphology='体呈长椭圆形而稍侧扁，全长可达 30 cm。'
                       '体色黄褐至红褐，腹部较浅；'
                       '背鳍与臀鳍呈黄色或橙色，尾鳍浅凹。'
                       '吻端较尖，口中等大，下颌略突出。',
            habit='栖息于珊瑚礁与礁缘，成鱼多单独或小群活动于较深处，'
                  '幼鱼则常见于浅水礁池与河口。'
                  '夜行性，夜间外出捕食鱼类与甲壳类，昼间藏于礁穴。',
            distribution='印度—太平洋：东非与红海至日本南部、'
                         '澳大利亚与法属波利尼西亚；中国台湾与南海有分布。'),
    16: dict(family='眶棘鲈科 Nemipteridae',
            morphology='体呈长椭圆形而侧扁，全长约 20～25 cm。'
                       '体背侧淡褐，腹部白色；'
                       '体侧具两条明显白色纵带，为其显著特征，故名双线。'
                       '头部具一条自眼后延伸的暗色带。',
            habit='栖息于砂泥底与礁石交界的过渡带，单独或成小群活动。'
                  '以底栖甲壳类、多毛类与小鱼为食，'
                  '用下位口翻搅砂面取食。',
            distribution='印度—西太平洋：安达曼海至日本南部、'
                         '菲律宾与澳大利亚北部；中国南海与台湾有分布。'),
    17: dict(family='鹦嘴鱼科 Scaridae',
            # 关键：官方仅标注到科级，无确定种名，文案必须按科级描述
            morphology='体呈长椭圆形而略侧扁，属中型至大型珊瑚礁鱼类，'
                       '成体全长多在 20～40 cm。'
                       '上下颌愈合形成形似鸟喙的齿板，是本科最显著的鉴定特征，'
                       '也因此得名。体色多样，多呈绿、蓝、褐或红褐色，'
                       '部分个体体侧具不规则斑纹。'
                       '本类群在 Fish4Knowledge 数据集中仅标注至科级（Scaridae），'
                       '未细分到种，故此处按科级特征描述。',
            habit='白天在珊瑚礁与藻床间活动，用喙状齿板刮食礁面藻类，'
                  '并常将珊瑚骨骼咬碎后排出，是珊瑚礁生物侵蚀与'
                  '砂质沉积物生成的重要参与者。'
                  '夜间部分种类会分泌黏液囊包裹身体以遮蔽气味、躲避捕食者。'
                  '多数种类存在体型与体色的阶段性变化，'
                  '并属雌雄同体先雌后雄型。',
            distribution='鹦嘴鱼科广布于全球热带与亚热带珊瑚礁海域，'
                         '印度—太平洋区物种多样性最高；'
                         '中国台湾、海南与南海诸岛礁区均有分布。'),
    18: dict(family='单鳍鱼科 Pempheridae',
            morphology='体呈卵圆形而侧扁，全长约 15～18 cm。'
                       '体色银铜色至淡红褐，体侧各鳍基部与边缘色深。'
                       '背鳍短小，臀鳍基部长，向后延伸至尾柄。'
                       '眼大而突出，为夜行性生活提供良好视觉。',
            habit='昼间成密集的大群躲藏于礁穴、礁檐与沉船内部，'
                  '入夜后成群游出，至水层中上层捕食浮游动物与小型甲壳类。'
                  '群聚行为极为明显，受惊时整群同步变换方向。',
            distribution='印度—太平洋：红海与东非至日本南部、'
                         '澳大利亚与马绍尔群岛；中国台湾与南海有分布。'),
    19: dict(family='镰鱼科 Zanclidae',
            morphology='体甚侧扁而高，呈盘状，全长约 20 cm。'
                       '体色以白、黑、黄三色构成鲜明图案：'
                       '体侧具两条黑色宽垂直带，吻部向前延伸呈管状，'
                       '背鳍第一鳍条延长为长丝状（故名镰鱼）。'
                       '外形与蝴蝶鱼相似，但亲缘关系较远，属单型科。',
            habit='栖息于礁坡与礁池，单独或成对活动，'
                  '以细长的吻探入礁隙取食海绵、苔藓虫与藻类。'
                  '游泳姿态缓慢优雅，常与蝴蝶鱼混群。',
            distribution='印度—太平洋：东非与红海至夏威夷、'
                         '日本南部与澳大利亚；中国台湾与南海有分布。'),
    20: dict(family='雀鲷科 Pomacentridae',
            morphology='体呈卵圆形而侧扁，全长约 8～9 cm，'
                       '是本数据集中体型最小、样本量最少的物种之一。'
                       '成鱼体色深褐至黑褐，头侧与吻端色更深；'
                       '背鳍后部与臀鳍具黑色边缘。'
                       '颊部与鳃盖具明显黑色斑点，为重要识别特征。',
            habit='领域性很强，常固守一小片分枝珊瑚或礁石缝隙。'
                  '以藻类与小型无脊椎动物为食。'
                  '因个体小且色暗、栖息于礁枝间而难以观察，'
                  '野外记录相对稀少。',
            distribution='西太平洋：菲律宾、印度尼西亚东部至'
                         '中国台湾与南海诸岛；记录相对零散。'),
    21: dict(family='鳞鲀科 Balistidae',
            morphology='体呈长椭圆形而侧扁，全长约 25 cm。'
                       '体色深褐至墨绿，体侧具多条波状橙色至黄色的纵纹'
                       '（故名黄纹）。'
                       '第一背鳍具三枚硬棘，第一棘粗大且可锁定竖立；'
                       '尾柄两侧具数行黑色小棘。',
            habit='栖息于珊瑚礁与礁缘，单独活动，领域性强。'
                  '以海胆、甲壳类、软体动物与小鱼为食，'
                  '具强有力的齿可咬碎海胆棘刺。'
                  '受威胁时竖立背鳍棘并发出威吓声。',
            distribution='印度—太平洋：红海与东非至日本南部、'
                         '大堡礁与社会群岛；中国台湾与南海有分布。'),
    22: dict(family='蓝子鱼科 Siganidae',
            morphology='体呈卵圆形而侧扁，全长约 20～25 cm。'
                       '体色灰褐至黄褐，体侧密布细小浅色斑点，'
                       '背部色较深，腹部银白。'
                       '背鳍与臀鳍的每一硬棘均具毒腺，'
                       '被刺伤后会引起剧烈疼痛。',
            habit='栖息于珊瑚礁、藻床与河口等浅水区，'
                  '幼鱼常成群进入河口与红树林。'
                  '以藻类为主要食物。'
                  '受威胁时张开各鳍并将毒棘竖立，是有效的防御手段。',
            distribution='西太平洋：日本南部至澳大利亚东部，'
                         '包括中国沿岸、台湾与南海；'
                         '中国东南沿海与河口区常见。'),
}


SYSTEM_CONFIGS = [
    ('guest_quota', '3', 'int', '游客免登录试用次数上限'),
    ('max_file_size_mb', '10', 'int', '单张上传文件体积上限（MB）'),
    ('batch_upload_limit', '9', 'int', '批量上传张数上限'),
    ('low_confidence_threshold', '0.6', 'float', '低置信度提示阈值'),
    ('image_retention_days', '180', 'int', '上传原图保留天数'),
]


def seed_species(db) -> tuple[int, int]:
    added = updated = 0
    now = int(time.time())
    for s in SPECIES:
        txt = SPECIES_TEXT[s.class_index]
        row = db.scalar(select(SpeciesModel).where(
            SpeciesModel.class_index == s.class_index))
        if row is None:
            db.add(SpeciesModel(
                id=s.class_index + 1,
                class_index=s.class_index,
                cn_name=s.cn_name,
                latin_name=s.sci_name,
                common_name=s.dir_name,
                morphology=txt['morphology'],
                habit=txt['habit'],
                distribution=txt['distribution'],
                image_path=None,
                created_at=now, updated_at=now))
            added += 1
        else:
            row.cn_name = s.cn_name
            row.latin_name = s.sci_name
            row.morphology = txt['morphology']
            row.habit = txt['habit']
            row.distribution = txt['distribution']
            row.updated_at = now
            updated += 1
    db.flush()
    return added, updated


def seed_configs(db) -> tuple[int, int]:
    added = updated = 0
    now = int(time.time())
    for key, val, vtype, desc in SYSTEM_CONFIGS:
        row = db.get(SystemConfig, key)
        if row is None:
            db.add(SystemConfig(config_key=key, value=val, value_type=vtype,
                                description=desc, updated_by=None, updated_at=now))
            added += 1
        else:
            row.value = val
            row.value_type = vtype
            row.description = desc
            row.updated_at = now
            updated += 1
    db.flush()
    return added, updated


def main() -> int:
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    problems = []

    print('=' * 72)
    print('海瞳鱼鉴 · 种子数据初始化')
    print('=' * 72)

    a, u = seed_species(db)
    print(f'  species       新增 {a} / 更新 {u}   （期望合计 23）')
    if a + u != 23:
        problems.append(f'species 合计 {a + u}，期望 23')

    # fish_18 必须按科级描述 —— 校验文案里不含具体种名杜撰
    s18 = db.scalar(select(SpeciesModel).where(SpeciesModel.class_index == 17))
    genus_level_ok = s18 is not None and 'Scaridae' in s18.latin_name and \
        '科级' in s18.morphology
    print(f'  {"✓" if genus_level_ok else "✗"} fish_18(class_index=17) 按科级描述：'
          f'{s18.latin_name if s18 else "缺失"}')
    if not genus_level_ok:
        problems.append('fish_18 未按科级描述')

    a2, u2 = seed_configs(db)
    print(f'  system_config 新增 {a2} / 更新 {u2}   （期望合计 {len(SYSTEM_CONFIGS)}）')
    if a2 + u2 != len(SYSTEM_CONFIGS):
        problems.append('system_config 数量不符')

    admin = ensure_admin(db)
    print(f'  管理员         {admin.username} / role={admin.role} / status={admin.status}')

    db.commit()

    # 回读核对
    n_sp = db.scalar(select(__import__('sqlalchemy').func.count()).select_from(SpeciesModel))
    n_cf = db.scalar(select(__import__('sqlalchemy').func.count()).select_from(SystemConfig))
    n_us = db.scalar(select(__import__('sqlalchemy').func.count()).select_from(User))
    print()
    print(f'  回读：species={n_sp}  system_config={n_cf}  user={n_us}')
    if n_sp != 23:
        problems.append(f'species 回读 {n_sp}')
    if n_cf != len(SYSTEM_CONFIGS):
        problems.append(f'system_config 回读 {n_cf}')

    # class_index 连续性
    idxs = sorted(s.class_index for s in db.scalars(select(SpeciesModel)))
    cont = idxs == list(range(23))
    print(f'  {"✓" if cont else "✗"} class_index 取值集合恰为 0..22（D7 §8.2 C-02）')
    if not cont:
        problems.append(f'class_index 不连续：{idxs}')

    db.close()
    print()
    if problems:
        print(f'  ✗ 发现 {len(problems)} 个问题：')
        for p in problems:
            print(f'      - {p}')
        return 1
    print('  ✓ 种子数据初始化完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
