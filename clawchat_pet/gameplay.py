"""Project one scene-neutral growth snapshot into selectable gameplay scenes.

Scenes are read-only adapters.  They name and narrate already-settled growth;
they never participate in Hermes intake, deduplication, or reward formulas.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .growth import GrowthFact, GrowthSnapshot

DEFAULT_SCENE_ID = "xianxia"

XIANXIA_TOOL_LABELS = {
    "command-execution": "御剑诀",
    "file-inspection": "天机推演",
    "file-editing": "符箓编纂",
    "mission-planning": "执事录",
    "remote-research": "神识外放",
    "browser-operation": "分身入世",
    "visual-observation": "灵目观世",
    "image-creation": "幻术造化",
    "code-simulation": "内景推演",
    "delegation": "分神化身",
    "history-retrieval": "追溯前尘",
    "scheduled-watch": "分身值守",
    "skill-learning": "传承参悟",
    "memory-keeping": "识海铭刻",
}

XIANXIA_ASSET_LABELS = {
    "command-execution": "本命飞剑",
    "file-inspection": "观天灵镜",
    "file-editing": "符笔",
    "mission-planning": "执事玉简",
    "remote-research": "观天盘",
    "browser-operation": "云舟",
    "image-creation": "幻月灯",
    "scheduled-watch": "值守傀儡",
    "skill-learning": "传承玉匣",
}

STAR_TOOL_LABELS = {
    "command-execution": "推进器调试",
    "file-inspection": "星图解码",
    "file-editing": "航志编纂",
    "mission-planning": "任务编排",
    "remote-research": "深空扫描",
    "browser-operation": "探测艇巡航",
    "visual-observation": "光谱观测",
    "image-creation": "全息构造",
    "code-simulation": "轨道模拟",
    "delegation": "僚机协作",
    "history-retrieval": "航迹回溯",
    "scheduled-watch": "自动值守",
    "skill-learning": "协议研习",
    "memory-keeping": "航行档案",
}

STAR_ASSET_LABELS = {
    "command-execution": "主推进器",
    "file-inspection": "星图终端",
    "file-editing": "航志仪",
    "mission-planning": "任务面板",
    "remote-research": "深空阵列",
    "browser-operation": "探测艇",
    "image-creation": "全息投影仪",
    "scheduled-watch": "值守无人机",
    "skill-learning": "协议数据库",
}

STAR_STAGE_LABELS = tuple(
    [f"航校学员 {level}" for level in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")]
    + [f"近地领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
    + [f"行星领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
    + [f"恒星领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
    + ["深空航行门槛", "跃迁试航", "星门校准"]
    + [f"银河领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
)

XIANXIA_STAGE_LABELS = tuple(
    [f"炼气{level}层" for level in range(1, 10)]
    + [f"筑基{phase}" for phase in ("初期", "中期", "后期", "圆满")]
    + [f"金丹{phase}" for phase in ("初期", "中期", "后期", "圆满")]
    + [f"元婴{phase}" for phase in ("初期", "中期", "后期", "圆满")]
    + ["化神门槛", "化神·雷劫试炼", "化神·元神试炼"]
    + [f"化神{phase}" for phase in ("初期", "中期", "后期", "圆满")]
)

XIANXIA_STAGE_BADGES = tuple(
    "炼气" if index < 9
    else "筑基" if index < 13
    else "金丹" if index < 17
    else "元婴" if index < 21
    else "试炼" if index < 24
    else "化神"
    for index in range(len(XIANXIA_STAGE_LABELS))
)

STAR_STAGE_BADGES = tuple(
    "航校" if index < 9
    else "近地" if index < 13
    else "行星" if index < 17
    else "恒星" if index < 21
    else "试航" if index < 24
    else "银河"
    for index in range(len(STAR_STAGE_LABELS))
)


class GameplayScene(Protocol):
    """Internal seam implemented by each gameplay-scene adapter."""

    id: str
    name: str

    def summary(self) -> dict[str, Any]: ...

    def project(
        self,
        growth: GrowthSnapshot,
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SceneDefinition:
    id: str
    name: str
    description: str
    stage_labels: tuple[str, ...]
    stage_badges: tuple[str, ...]
    end_label: str
    meter_labels: Mapping[str, str]
    strategy_labels: Mapping[str, str]
    action_labels: Mapping[str, str]
    tool_labels: Mapping[str, str]
    unknown_tool_label: str
    asset_labels: Mapping[str, str]
    unknown_asset_label: str
    grade_labels: Mapping[str, str]
    hint_templates: Mapping[str, str]
    chronicle_templates: Mapping[str, str]
    voice_lines: Mapping[str, tuple[str, ...]]
    chronicle_title: str
    default_skin_id: str
    skin_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.stage_badges) != len(self.stage_labels):
            raise ValueError(f"scene {self.id!r} must define one badge per stage")
        required_meters = {
            "primary", "risk", "stability", "insight", "strain", "fortune"
        }
        if required_meters - set(self.meter_labels):
            raise ValueError(f"scene {self.id!r} is missing meter labels")
        required_strategies = {
            "balanced", "advance", "stabilize", "learn", "recover"
        }
        if required_strategies - set(self.strategy_labels):
            raise ValueError(f"scene {self.id!r} is missing strategy labels")
        if {"trial_ready", "cap", "ready", "target"} - set(self.hint_templates):
            raise ValueError(f"scene {self.id!r} is missing hint templates")
        if "unknown" not in self.chronicle_templates:
            raise ValueError(f"scene {self.id!r} requires an unknown-event template")

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "default_skin_id": self.default_skin_id,
            "skin_ids": list(self.skin_ids),
        }

    def _tool_label(self, capability_id: str) -> str:
        return self.tool_labels.get(capability_id, self.unknown_tool_label)

    def _asset_label(self, capability_id: str, fallback: str) -> str:
        return self.asset_labels.get(
            capability_id, fallback or self.unknown_asset_label
        )

    def _badge(self, index: int) -> str:
        return self.stage_badges[index]

    def _hint(
        self,
        stage_label: str,
        next_label: str,
        ready: bool,
        kind: str,
        requirements: Mapping[str, Any],
    ) -> str:
        template_key = (
            "trial_ready" if kind == "trial" and ready
            else "cap" if kind == "cap"
            else "ready" if ready
            else "target"
        )
        return self.hint_templates[template_key].format(
            stage=stage_label,
            next=next_label,
            primary=requirements["primary"],
            risk=requirements["risk"],
            strain=requirements["strain"],
            stability=requirements["stability"],
            insight=requirements["insight"],
            primary_label=self.meter_labels["primary"],
            risk_label=self.meter_labels["risk"],
            strain_label=self.meter_labels["strain"],
            stability_label=self.meter_labels["stability"],
            insight_label=self.meter_labels["insight"],
        )

    def _voice(
        self,
        growth: GrowthSnapshot,
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        event = str(activity.get("state") or "idle")
        profile = personality.get("profile") or {}
        lines = profile.get("lines") or {}
        custom = lines.get(event)
        if custom:
            text = str(custom[0])
        else:
            pool = self.voice_lines.get(event) or self.voice_lines.get("idle") or ("我在。",)
            text = str(pool[0])
        latest_fact_at = (
            growth.recent_facts[-1].occurred_at if growth.recent_facts else 0.0
        )
        return {
            "speaker": str(pet.get("displayName") or "宠物"),
            "mood": event,
            "text": text,
            "ts": max(float(activity.get("ts") or 0), latest_fact_at),
            "event": event,
        }

    def _chronicle_text(self, fact: GrowthFact) -> str:
        data = fact.data
        capability_id = fact.capability_id
        template = self.chronicle_templates.get(
            fact.kind, self.chronicle_templates["unknown"]
        )
        stage_index = int(data.get("to_index") or 0)
        stage_index = max(0, min(stage_index, len(self.stage_labels) - 1))
        strategy_id = str(data.get("strategy_id") or "balanced")
        return template.format(
            tool=self._tool_label(capability_id),
            asset=self._asset_label(capability_id, ""),
            primary_gain=float(data.get("primary_gain") or 0),
            stage=self.stage_labels[stage_index],
            strategy=self.strategy_labels.get(
                strategy_id, self.strategy_labels["balanced"]
            ),
            level=int(data.get("level") or 1),
            idle_stage=int(data.get("stage") or 0),
        )

    def project(
        self,
        growth: GrowthSnapshot,
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        if growth.stage.total != len(self.stage_labels):
            raise ValueError(
                f"scene {self.id!r} does not label every shared growth stage"
            )
        index = growth.stage.index
        stage_label = self.stage_labels[index]
        next_label = (
            self.stage_labels[index + 1]
            if index + 1 < len(self.stage_labels)
            else self.end_label
        )
        kind = growth.stage.kind
        ready = growth.stage.ready
        requirements = growth.stage.requirements
        meters = [
            {
                "id": "primary", "label": self.meter_labels["primary"],
                "value": growth.dimensions["primary"].value,
                "max": growth.dimensions["primary"].maximum or 1.0,
                "tone": "primary",
            },
            {
                "id": "risk", "label": self.meter_labels["risk"],
                "value": growth.dimensions["risk"].value,
                "max": growth.dimensions["risk"].maximum or 100.0,
                "tone": "risk",
            },
        ]
        attributes = [
            {
                "id": key,
                "label": self.meter_labels[key],
                "value": growth.dimensions[key].value,
            }
            for key in ("stability", "insight", "strain", "fortune")
        ]
        strategy_id = growth.strategy.id
        choices = [
            {"id": choice, "label": self.strategy_labels[choice]}
            for choice in growth.strategy.choices
        ]
        activity_view = copy.deepcopy(dict(activity))
        current_capability_id = str(
            activity_view.pop("current_capability_id", "") or ""
        )
        chronicle_entries = []
        for fact in growth.recent_facts:
            chronicle_entries.append({
                "ts": fact.occurred_at,
                "kind": fact.kind,
                "text": self._chronicle_text(fact),
            })
        capabilities = []
        for capability_id, item in growth.capabilities.items():
            capabilities.append({
                "id": capability_id,
                "label": self._tool_label(capability_id),
                "level": item.level,
                "xp": item.xp,
                "xp_next": item.xp_next,
            })
        assets = []
        for capability_id, item in growth.assets.items():
            assets.append({
                "id": f"asset:{capability_id}",
                "label": self._asset_label(capability_id, ""),
                "level": item.level,
                "grade": self.grade_labels.get(item.tier, item.tier),
            })
        return {
            "schema_version": 1,
            "scene": self.summary(),
            "pet": copy.deepcopy(dict(pet)),
            "activity": {
                **activity_view,
                "label": self.action_labels.get(str(activity.get("state") or "idle"), ""),
                "capability": {
                    "id": current_capability_id,
                    "label": self._tool_label(current_capability_id),
                } if current_capability_id else None,
            },
            "stage": {
                "id": f"stage-{index:02d}",
                "index": index,
                "total": len(self.stage_labels),
                "label": stage_label,
                "badge": self._badge(index),
                "kind": kind,
                "next_label": next_label,
                "ready": ready,
                "hint": self._hint(stage_label, next_label, ready, kind, requirements),
                "requirements": dict(requirements),
            },
            "meters": meters,
            "attributes": attributes,
            "strategy": {
                "id": strategy_id,
                "label": self.strategy_labels[strategy_id],
                "choices": choices,
            },
            "voice": self._voice(growth, activity, pet, personality),
            "chronicle": {
                "title": self.chronicle_title,
                "entries": chronicle_entries,
            },
            "capabilities": capabilities,
            "assets": assets,
        }


XIANXIA_SCENE = SceneDefinition(
    id="xianxia",
    name="修仙",
    description="境界、灵气、心魔、历练与道场纪事。",
    stage_labels=XIANXIA_STAGE_LABELS,
    stage_badges=XIANXIA_STAGE_BADGES,
    end_label="更高天地待开启",
    meter_labels={
        "primary": "灵气", "risk": "心魔", "stability": "道心",
        "insight": "悟性", "strain": "疲劳", "fortune": "气运",
    },
    strategy_labels={
        "balanced": "入定", "advance": "冲关", "stabilize": "淬心",
        "learn": "悟道", "recover": "调息",
    },
    action_labels={
        "idle": "入定吐纳", "review": "推演天机", "run": "御剑历练",
        "wave": "收束因果", "failed": "心魔侵扰", "waiting": "静候法旨",
        "jump": "灵光乍现", "unknown": "因果未明", "subagent": "分神化身",
    },
    tool_labels=XIANXIA_TOOL_LABELS,
    unknown_tool_label="无名术法",
    asset_labels=XIANXIA_ASSET_LABELS,
    unknown_asset_label="无名法器",
    grade_labels={"basic": "凡器", "enhanced": "灵器", "core": "法宝"},
    hint_templates={
        "trial_ready": "{stage}可结算；等待下一次成功历练推进至{next}。",
        "cap": "已到当前天地边界；更高境界待开启。",
        "ready": "可突破至{next}",
        "target": (
            "目标：{next}。需{primary_label} {primary}，{risk_label}≤{risk}，"
            "{strain_label}≤{strain}，{stability_label}≥{stability}，"
            "{insight_label}≥{insight}。"
        ),
    },
    chronicle_templates={
        "born": "宠物入驻 clawchat-pet 道场，开始吐纳修行。",
        "work_started": "宠物开始施展{tool}。",
        "work_succeeded": "历练功成：{tool}，灵气 +{primary_gain:.1f}。",
        "work_failed": "历练受阻：{tool}，心魔滋生。",
        "work_recovered": "宠物斩去杂念，破除一缕心魔。",
        "stage_advanced": "气机圆满，宠物突破至{stage}。",
        "strategy_selected": "今日修行策略改为{strategy}。",
        "idle_decay": "久未温养，道场状态发生第 {idle_stage} 阶段变化。",
        "stage_regressed": "道基浮动，宠物退回{stage}。",
        "capability_advanced": "{tool}小有所成，提升至 Lv.{level}。",
        "asset_advanced": "{asset}完成一次淬炼。",
        "unknown": "记录到一项尚未命名的成长事实。",
    },
    voice_lines={
        "idle": ("我在。灵息很稳。",),
        "review": ("我在推演这条因果线。",),
        "run": ("正在历练，别眨眼。",),
        "wave": ("功成，记一笔。",),
        "failed": ("有反噬，但还能压住。",),
        "waiting": ("我收剑等你确认。",),
        "unknown": ("这道因果尚不明确。",),
        "subagent": ("分神化身已经出发。",),
    },
    chronicle_title="道场纪事",
    default_skin_id="qingming",
    skin_ids=("qingming", "chiyan", "xuanshui"),
)

STAR_VOYAGE_SCENE = SceneDefinition(
    id="star-voyage",
    name="星际远征",
    description="把共享成长解释为航程、舰体状态、科研与远征任务。",
    stage_labels=STAR_STAGE_LABELS,
    stage_badges=STAR_STAGE_BADGES,
    end_label="更远星域待开放",
    meter_labels={
        "primary": "航程数据", "risk": "故障风险", "stability": "舰体稳定",
        "insight": "科研", "strain": "负荷", "fortune": "导航运",
    },
    strategy_labels={
        "balanced": "标准巡航", "advance": "全速跃迁", "stabilize": "加固护盾",
        "learn": "深空扫描", "recover": "停泊检修",
    },
    action_labels={
        "idle": "停泊待命", "review": "分析星图", "run": "执行远征",
        "wave": "任务归航", "failed": "系统告警", "waiting": "等待指令",
        "jump": "发现航线", "unknown": "信号未明", "subagent": "僚机协作",
    },
    tool_labels=STAR_TOOL_LABELS,
    unknown_tool_label="未分类任务",
    asset_labels=STAR_ASSET_LABELS,
    unknown_asset_label="通用任务模块",
    grade_labels={"basic": "基础", "enhanced": "增强", "core": "核心"},
    hint_templates={
        "trial_ready": "{stage}准备就绪；下一次任务成功将完成试航并进入{next}。",
        "cap": "已抵达当前星图边界；更远航区尚待开放。",
        "ready": "航行条件已满足，可晋升至{next}。",
        "target": (
            "目标：{next}。需{primary_label} {primary}，{risk_label}≤{risk}，"
            "{strain_label}≤{strain}，{stability_label}≥{stability}，"
            "{insight_label}≥{insight}。"
        ),
    },
    chronicle_templates={
        "born": "宠物加入远征基地，开始准备首航。",
        "work_started": "远征任务启动：{tool}。",
        "work_succeeded": "任务完成：{tool}，航程数据 +{primary_gain:.1f}。",
        "work_failed": "任务受阻：{tool}，故障风险上升。",
        "work_recovered": "宠物排除一处隐患，舰体稳定得到提升。",
        "stage_advanced": "航程达标，宠物晋升至{stage}。",
        "strategy_selected": "今日航行策略改为{strategy}。",
        "idle_decay": "长期停泊触发第 {idle_stage} 阶段校准。",
        "stage_regressed": "航行状态回退至{stage}。",
        "capability_advanced": "{tool}熟练度提升至 Lv.{level}。",
        "asset_advanced": "{asset}完成一次模块升级。",
        "unknown": "记录到一项尚未分类的成长事实。",
    },
    voice_lines={
        "idle": ("航线稳定，随时可以出发。",),
        "review": ("我正在分析这片星图。",),
        "run": ("远征任务已启动。",),
        "wave": ("任务完成，正在归航。",),
        "failed": ("系统有些波动，我会重新校准。",),
        "waiting": ("指令未确认，我保持待命。",),
        "unknown": ("信号还不明确，暂不下结论。",),
        "subagent": ("僚机已经出发协作。",),
    },
    chronicle_title="远征日志",
    default_skin_id="xinghai",
    skin_ids=("xinghai", "chenhui"),
)


class GameplayScenes:
    """Deep in-process module for cataloguing and projecting gameplay scenes."""

    def __init__(self, scenes: tuple[GameplayScene, ...] | None = None) -> None:
        registered = scenes or (XIANXIA_SCENE, STAR_VOYAGE_SCENE)
        self._scenes: dict[str, GameplayScene] = {}
        for scene in registered:
            if scene.id in self._scenes:
                raise ValueError(f"duplicate gameplay scene: {scene.id}")
            self._scenes[scene.id] = scene
        if DEFAULT_SCENE_ID not in self._scenes:
            raise ValueError(f"default gameplay scene {DEFAULT_SCENE_ID!r} is required")

    def get(self, scene_id: str) -> GameplayScene:
        try:
            return self._scenes[scene_id]
        except KeyError:
            raise KeyError(f"unknown gameplay scene: {scene_id}") from None

    def catalog(self, active_scene: str) -> dict[str, Any]:
        active_scene = active_scene if active_scene in self._scenes else DEFAULT_SCENE_ID
        scenes = []
        for scene in self._scenes.values():
            summary = scene.summary()
            summary["active"] = scene.id == active_scene
            scenes.append(summary)
        return {
            "current_scene": active_scene,
            "scenes": scenes,
            "count": len(scenes),
        }

    def project(
        self,
        scene_id: str,
        growth: GrowthSnapshot,
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.get(scene_id).project(growth, activity, pet, personality)
