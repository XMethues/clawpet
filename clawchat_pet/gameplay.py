"""Project one shared growth save into selectable gameplay scenes.

Scenes are read-only adapters.  They name and narrate already-settled growth;
they never participate in Hermes intake, deduplication, or reward formulas.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .simulator import (
    ARTIFACT_BY_TOOL,
    POLICY_NAMES,
    STRATEGY_ID_BY_POLICY,
    REALM_PATH,
    TECHNIQUE_BY_TOOL,
)

DEFAULT_SCENE_ID = "xianxia"

CAPABILITY_ID_BY_TOOL = {
    "terminal": "command-execution",
    "process": "command-execution",
    "read_file": "file-inspection",
    "search_files": "file-inspection",
    "write_file": "file-editing",
    "patch": "file-editing",
    "todo": "mission-planning",
    "web_search": "remote-research",
    "web_extract": "remote-research",
    "browser_navigate": "browser-operation",
    "browser_snapshot": "browser-operation",
    "browser_click": "browser-operation",
    "browser_type": "browser-operation",
    "browser_scroll": "browser-operation",
    "browser_vision": "visual-observation",
    "vision_analyze": "visual-observation",
    "image_generate": "image-creation",
    "execute_code": "code-simulation",
    "delegate_task": "delegation",
    "session_search": "history-retrieval",
    "cronjob": "scheduled-watch",
    "skill_view": "skill-learning",
    "skill_manage": "skill-learning",
    "memory": "memory-keeping",
}

STAR_TOOL_LABELS = {
    "terminal": "推进器调试",
    "process": "推进器调试",
    "read_file": "星图解码",
    "search_files": "星图解码",
    "write_file": "航志编纂",
    "patch": "航志编纂",
    "todo": "任务编排",
    "web_search": "深空扫描",
    "web_extract": "深空扫描",
    "browser_navigate": "探测艇巡航",
    "browser_snapshot": "探测艇巡航",
    "browser_click": "探测艇巡航",
    "browser_type": "探测艇巡航",
    "browser_scroll": "探测艇巡航",
    "browser_vision": "光谱观测",
    "vision_analyze": "光谱观测",
    "image_generate": "全息构造",
    "execute_code": "轨道模拟",
    "delegate_task": "僚机协作",
    "session_search": "航迹回溯",
    "cronjob": "自动值守",
    "skill_view": "协议研习",
    "skill_manage": "协议研习",
    "memory": "航行档案",
}

STAR_ASSET_LABELS = {
    "terminal": "主推进器",
    "process": "主推进器",
    "read_file": "星图终端",
    "search_files": "星图终端",
    "write_file": "航志仪",
    "patch": "航志仪",
    "todo": "任务面板",
    "web_search": "深空阵列",
    "web_extract": "深空阵列",
    "browser_navigate": "探测艇",
    "image_generate": "全息投影仪",
    "cronjob": "值守无人机",
    "skill_manage": "协议数据库",
}

STAR_STAGE_LABELS = tuple(
    [f"航校学员 {level}" for level in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")]
    + [f"近地领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
    + [f"行星领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
    + [f"恒星领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
    + ["深空航行门槛", "跃迁试航", "星门校准"]
    + [f"银河领航员·{phase}" for phase in ("初级", "中级", "高级", "资深")]
)

XIANXIA_STAGE_BADGES = tuple(
    "试炼"
    if str(item.get("kind") or "") in {"gate", "tribulation"}
    else "化神"
    if "化神" in str(item.get("label") or "")
    else str(item.get("phase") or item.get("label") or "")[:4]
    for item in REALM_PATH
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
        save: Mapping[str, Any],
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
    preserve_fact_text: bool = False

    def __post_init__(self) -> None:
        if len(self.stage_labels) != len(REALM_PATH):
            raise ValueError(
                f"scene {self.id!r} must define {len(REALM_PATH)} stage labels"
            )
        if len(self.stage_badges) != len(self.stage_labels):
            raise ValueError(f"scene {self.id!r} must define one badge per stage")
        required_meters = {
            "primary", "risk", "stability", "insight", "strain", "fortune"
        }
        if required_meters - set(self.meter_labels):
            raise ValueError(f"scene {self.id!r} is missing meter labels")
        if set(STRATEGY_ID_BY_POLICY.values()) - set(self.strategy_labels):
            raise ValueError(f"scene {self.id!r} is missing strategy labels")
        if {"trial_ready", "cap", "ready", "target"} - set(self.hint_templates):
            raise ValueError(f"scene {self.id!r} is missing hint templates")
        if "unknown" not in self.chronicle_templates and not self.preserve_fact_text:
            raise ValueError(f"scene {self.id!r} requires an unknown-event template")

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "default_skin_id": self.default_skin_id,
            "skin_ids": list(self.skin_ids),
        }

    def _tool_label(self, tool: str) -> str:
        return self.tool_labels.get(tool, self.unknown_tool_label)

    def _asset_label(self, tool: str, fallback: str) -> str:
        return self.asset_labels.get(tool, fallback or self.unknown_asset_label)

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
            "trial_ready" if kind == "tribulation" and ready
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
        save: Mapping[str, Any],
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        stored = copy.deepcopy(save.get("voice") or {})
        event = str(activity.get("state") or stored.get("event") or "idle")
        profile = personality.get("profile") or {}
        lines = profile.get("lines") or {}
        custom = lines.get(event) or lines.get(str(stored.get("event") or "idle"))
        if custom:
            text = str(custom[0])
        elif self.preserve_fact_text and stored.get("text"):
            text = str(stored["text"])
            event = str(stored.get("event") or event)
        else:
            pool = self.voice_lines.get(event) or self.voice_lines.get("idle") or ("我在。",)
            text = str(pool[0])
        return {
            "speaker": str(pet.get("displayName") or "宠物"),
            "mood": event,
            "text": text,
            "ts": float(stored.get("ts") or 0),
            "event": event,
        }

    def _chronicle_text(self, event: Mapping[str, Any]) -> str:
        text = str(event.get("text") or "")
        if self.preserve_fact_text:
            return text
        typ = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
        tool = str(data.get("tool") or "")
        template_key = (
            "breakthrough"
            if typ in {"minor_breakthrough", "major_breakthrough", "tribulation_pass"}
            else "idle"
            if typ in {"idle_decay", "idle_regression", "regression"}
            else typ
        )
        template = self.chronicle_templates.get(
            template_key, self.chronicle_templates["unknown"]
        )
        stage_index = int(data.get("stage_index") or 0)
        stage_index = max(0, min(stage_index, len(self.stage_labels) - 1))
        strategy_id = STRATEGY_ID_BY_POLICY.get(
            str(data.get("policy") or ""), "balanced"
        )
        rendered = template.format(
            tool=self._tool_label(tool),
            asset=self._asset_label(tool, ""),
            primary_gain=float(data.get("primary_gain") or 0),
            stage=self.stage_labels[stage_index],
            strategy=self.strategy_labels[strategy_id],
            level=int(data.get("level") or 1),
        )
        return rendered

    def project(
        self,
        save: Mapping[str, Any],
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        realm = save.get("realm") or {}
        stats = save.get("stats") or {}
        progress = save.get("progress") or {}
        target = progress.get("next_breakthrough") or {}
        index = int(realm.get("path_index") or 0)
        index = max(0, min(index, len(self.stage_labels) - 1))
        stage_label = self.stage_labels[index]
        next_label = (
            self.stage_labels[index + 1]
            if index + 1 < len(self.stage_labels)
            else self.end_label
        )
        kind = str(target.get("type") or "minor")
        ready = bool(realm.get("breakthrough_ready"))
        requirements = {
            "primary": target.get("qi_required", stats.get("max_qi", 0)),
            "risk": target.get("heart_demon_max", 0),
            "strain": target.get("fatigue_max", 0),
            "stability": target.get("dao_heart_min", 0),
            "insight": target.get("comprehension_min", 0),
        }
        meters = [
            {
                "id": "primary", "label": self.meter_labels["primary"],
                "value": float(stats.get("qi", 0)),
                "max": float(stats.get("max_qi", 1)), "tone": "primary",
            },
            {
                "id": "risk", "label": self.meter_labels["risk"],
                "value": float(stats.get("heart_demon", 0)),
                "max": 100.0, "tone": "risk",
            },
        ]
        attributes = [
            {"id": key, "label": self.meter_labels[key], "value": float(stats.get(source, 0))}
            for key, source in (
                ("stability", "dao_heart"),
                ("insight", "comprehension"),
                ("strain", "fatigue"),
                ("fortune", "fate"),
            )
        ]
        current_policy = str((save.get("policy") or {}).get("name") or POLICY_NAMES[0])
        strategy_id = STRATEGY_ID_BY_POLICY.get(current_policy, "balanced")
        choices = [
            {
                "id": STRATEGY_ID_BY_POLICY[name],
                "label": self.strategy_labels[STRATEGY_ID_BY_POLICY[name]],
            }
            for name in POLICY_NAMES
        ]
        activity_view = copy.deepcopy(dict(activity))
        current_tool = str(activity_view.pop("current_tool", "") or "")
        chronicle_entries = []
        for event in save.get("event_log") or []:
            chronicle_entries.append({
                "ts": float(event.get("ts") or 0),
                "kind": str(event.get("type") or "unknown"),
                "text": self._chronicle_text(event),
            })
        capabilities = []
        for stored_name, item in (save.get("techniques") or {}).items():
            tool = str(item.get("source") or "")
            capabilities.append({
                "id": CAPABILITY_ID_BY_TOOL.get(tool, f"tool:{tool or stored_name}"),
                "label": self._tool_label(tool) if tool else str(stored_name),
                "level": int(item.get("level") or 1),
                "xp": float(item.get("xp") or 0),
                "xp_next": float(item.get("xp_next") or 0),
            })
        assets = []
        for stored_name, item in (save.get("artifacts") or {}).items():
            tool = str(item.get("bound_tool") or "")
            grade = str(item.get("grade") or "")
            grade = self.grade_labels.get(grade, grade)
            assets.append({
                "id": f"asset:{CAPABILITY_ID_BY_TOOL.get(tool, tool or stored_name)}",
                "label": self._asset_label(tool, str(stored_name)),
                "level": int(item.get("level") or 1),
                "grade": grade,
            })
        return {
            "schema_version": 1,
            "scene": self.summary(),
            "pet": copy.deepcopy(dict(pet)),
            "activity": {
                **activity_view,
                "label": self.action_labels.get(str(activity.get("state") or "idle"), ""),
                "capability": {
                    "id": CAPABILITY_ID_BY_TOOL.get(current_tool, f"tool:{current_tool}"),
                    "label": self._tool_label(current_tool),
                } if current_tool else None,
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
                "requirements": requirements,
            },
            "meters": meters,
            "attributes": attributes,
            "strategy": {
                "id": strategy_id,
                "label": self.strategy_labels[strategy_id],
                "choices": choices,
            },
            "voice": self._voice(save, activity, pet, personality),
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
    stage_labels=tuple(str(item["label"]) for item in REALM_PATH),
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
    tool_labels=TECHNIQUE_BY_TOOL,
    unknown_tool_label="无名术法",
    asset_labels={tool: item[0] for tool, item in ARTIFACT_BY_TOOL.items()},
    unknown_asset_label="无名法器",
    grade_labels={},
    hint_templates={
        "trial_ready": "{stage}可结算；等待下一次成功历练或顿悟推进至{next}。",
        "cap": "已到当前天地边界；更高境界待开启。",
        "ready": "可突破至{next}",
        "target": (
            "目标：{next}。需{primary_label} {primary}，{risk_label}≤{risk}，"
            "{strain_label}≤{strain}，{stability_label}≥{stability}，"
            "{insight_label}≥{insight}。"
        ),
    },
    chronicle_templates={},
    voice_lines={},
    chronicle_title="道场纪事",
    default_skin_id="qingming",
    skin_ids=("qingming", "chiyan", "xuanshui"),
    preserve_fact_text=True,
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
    grade_labels={"凡器": "基础", "灵器": "增强", "法宝": "核心"},
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
        "birth": "宠物加入远征基地，开始准备首航。",
        "tool_success": "任务完成：{tool}，航程数据 +{primary_gain:.1f}。",
        "tool_failed": "任务受阻：{tool}，故障风险上升。",
        "review": "宠物分析星图片刻，科研数据微增。",
        "recovered": "宠物排除一处隐患，舰体稳定得到提升。",
        "waiting": "指令尚未确认，宠物保持待命。",
        "insight": "新的航线灵感闪现，宠物记录了坐标。",
        "breakthrough": "航程达标，宠物晋升至{stage}。",
        "policy": "今日航行策略改为{strategy}。",
        "idle": "长期停泊使航行状态有所衰减，宠物正在重新校准。",
        "technique_up": "{tool}熟练度提升至 Lv.{level}。",
        "artifact_up": "{asset}完成一次模块升级。",
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
        save: Mapping[str, Any],
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.get(scene_id).project(save, activity, pet, personality)
