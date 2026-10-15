# Workflow Simulation Configuration

This file parameterizes the Kanban/Twig-style workflow simulator (`simulate_flow.py`). It defines the workflow states, standard human-driven durations, capacity limits, WIP limits, and stage multipliers for human, AI-assisted, and Agentic AI work items.

## How to Customize
You can adjust the parameters inside the JSON block below to explore different operating system configurations and observe how bottlenecks shift.

- **`enable_wip_limits`**: When `false`, issues pile up at human review and testing boundaries, demonstrating Yuval's POV on AI speed causing downstream queues. Set to `true` to observe how WIP limits stabilize flow and cycle times.
- **`stage_multipliers`**: Map representing the duration coefficient for each issue label per stage.
  - `Code Review` and `Specify/Plan` are human-in-the-loop (1.0 for all).
  - `Implement` is highly accelerated (0.33 for AI-coding-assist, 0.1 for Agentic AI).
  - `test and fix` is moderately accelerated.
- **`capacities`**: Represents the number of concurrent items that can be processed at that stage due to staffing constraints.

```json
{
  "simulation_days": 90,
  "sprint_length_days": 14,
  "enable_wip_limits": false,
  "epic_min_stories": 3,
  "epic_max_stories": 20,
  "workflow_order": [
    "Open",
    "To Do",
    "Specify/Plan",
    "Ready to Implement",
    "Next",
    "Implement",
    "Code Review",
    "Ready for Testing",
    "test and fix",
    "Ready for release",
    "Monitor/Adapt/Learn",
    "Done"
  ],
  "wip_limits": {
    "Specify/Plan": 3,
    "Ready to Implement": 10,
    "Next": 3,
    "Implement": 4,
    "Code Review": 2,
    "Ready for Testing": 5,
    "test and fix": 2,
    "Ready for release": 5,
    "Monitor/Adapt/Learn": 3
  },
  "base_durations": {
    "Specify/Plan": 0.5,
    "Ready to Implement": 0.0,
    "Next": 0.0,
    "Implement": 6.0,
    "Code Review": 2.0,
    "Ready for Testing": 0.5,
    "test and fix": 3.0,
    "Ready for release": 1.0,
    "Monitor/Adapt/Learn": 2.0
  },
  "stage_multipliers": {
    "Specify/Plan": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    },
    "Ready to Implement": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    },
    "Next": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    },
    "Implement": {
      "human": 1.0,
      "ai-coding-assist": 0.33,
      "agentic-ai": 0.1
    },
    "Code Review": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    },
    "Ready for Testing": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    },
    "test and fix": {
      "human": 1.0,
      "ai-coding-assist": 0.5,
      "agentic-ai": 0.2
    },
    "Ready for release": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    },
    "Monitor/Adapt/Learn": {
      "human": 1.0,
      "ai-coding-assist": 1.0,
      "agentic-ai": 1.0
    }
  },
  "capacities": {
    "Specify/Plan": 2,
    "Implement": 4,
    "Code Review": 2,
    "test and fix": 2,
    "Monitor/Adapt/Learn": 2
  },
  "scenarios": [
    {
      "folder": "1_local_optimization_trap",
      "description": "No WIP limits, AI implementation is highly accelerated but human review/testing is a bottleneck.",
      "opts": {
        "wip_limits": false,
        "ai_review": false,
        "ai_test": false,
        "quality_crash": false,
        "upstream_starvation": false
      }
    },
    {
      "folder": "2_balanced_flow",
      "description": "WIP limits enabled, stabilizing queues and cycle times.",
      "opts": {
        "wip_limits": true,
        "ai_review": false,
        "ai_test": false,
        "quality_crash": false,
        "upstream_starvation": false
      }
    },
    {
      "folder": "3_traditional_baseline",
      "description": "All work items take standard human duration (no AI acceleration).",
      "opts": {
        "wip_limits": false,
        "all_human": true,
        "ai_review": false,
        "ai_test": false,
        "quality_crash": false,
        "upstream_starvation": false
      }
    },
    {
      "folder": "4_balanced_ai_operating_model",
      "description": "AI-assisted code review and testing matching implementation speed.",
      "opts": {
        "wip_limits": false,
        "ai_review": true,
        "ai_test": true,
        "quality_crash": false,
        "upstream_starvation": false
      }
    },
    {
      "folder": "5_hyper_velocity_disaster",
      "description": "Agentic AI hyper-development speed (20x) with human bottlenecks and double feed rate.",
      "opts": {
        "wip_limits": false,
        "hyper_velocity": true,
        "ai_review": false,
        "ai_test": false,
        "quality_crash": false,
        "upstream_starvation": false
      }
    },
    {
      "folder": "6_hyper_velocity_quality_crash",
      "description": "Hyper-velocity development with testing rushed/forced to work at 5x speed, leading to high regression bug injection rate (35%).",
      "opts": {
        "wip_limits": false,
        "hyper_velocity": true,
        "ai_review": false,
        "ai_test": true,
        "quality_crash": true,
        "upstream_starvation": false
      }
    },
    {
      "folder": "7_techdebt_underload",
      "description": "Fast downstream execution but slow product planning (starvation) forces developers to inject techdebt and low-priority features to stay occupied.",
      "opts": {
        "wip_limits": false,
        "ai_review": true,
        "ai_test": true,
        "quality_crash": false,
        "upstream_starvation": true
      }
    },
    {
      "folder": "8_balanced_ai_with_wip_limits",
      "description": "The ideal operating model: pull both levers at once — AI-assisted review/testing elevate the human constraint AND WIP limits cap work-in-progress. Highest throughput with the shortest, most stable cycle time.",
      "opts": {
        "wip_limits": true,
        "ai_review": true,
        "ai_test": true,
        "quality_crash": false,
        "upstream_starvation": false
      }
    },
    {
      "folder": "9_safe_native_ai_transition",
      "description": "SAFe Feature, Epic, and Story lifecycle transition over 6 months: 2 months Legacy, 2 months AI coding/testing acceleration, 2 months Native AI with product-organized teams.",
      "opts": {
        "safe_native_ai": true,
        "simulation_days": 180
      }
    },
    {
      "folder": "10_sprint_carryover_and_predictability",
      "description": "Sprint carryover and predictability scenario testing multi-sprint item movements and mid-sprint scope additions.",
      "opts": {
        "wip_limits": false,
        "quality_crash": true,
        "simulation_days": 90
      }
    }
  ]
}
```
