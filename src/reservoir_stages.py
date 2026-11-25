"""水库工程示例工序配置；权重不是合同工程量或验收标准。"""
RESERVOIR_STAGES = [
    dict(id='preparation', name='施工准备与临时道路', weight=5, visibility='exterior', hint='施工便道、场地平整、施工平台；临建存在不等于准备全部完成'),
    dict(id='dam_foundation', name='坝基开挖及处理', weight=10, visibility='hidden', hint='坝基开挖面、清基、灌浆设备；隐蔽处理及质量无法从外观确认'),
    dict(id='diversion', name='导流与围堰', weight=10, visibility='exterior', hint='围堰、导流明渠、导流洞洞口；围堰拆除可能是正常工序转换'),
    dict(id='dam_body', name='大坝主体', weight=40, visibility='exterior', hint='先识别土石坝/混凝土坝等可见坝型；土石坝填筑层及碾压面，混凝土坝仓面、模板、浇筑段；不凭照片估计体积'),
    dict(id='spillway', name='溢洪道', weight=15, visibility='exterior', hint='进水渠、控制段、泄槽、消能设施、模板钢筋及混凝土成型面'),
    dict(id='intake_outlet', name='取放水建筑物', weight=10, visibility='hidden', hint='取水塔、放水洞口、管道及出口；地下段或水下段不可见时不推断'),
    dict(id='electromechanical', name='金属结构及机电安装', weight=5, visibility='hidden', hint='闸门、启闭机及设备可见安装；不能仅凭外观判断调试或验收'),
    dict(id='ancillary', name='护坡排水及附属工程', weight=5, visibility='exterior', hint='护坡、排水沟、坝顶道路、绿化及场地恢复'),
]
