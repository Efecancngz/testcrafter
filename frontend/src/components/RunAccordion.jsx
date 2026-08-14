import { useState } from "react";
import Screenshot from "./Screenshot";

const RUN_ICON = { passed: "✓", running: "●", pending: "○", failed: "✗" };
const STEP_ICON = { passed: "✓", failed: "✗" };

function parsedScenarioSteps(scenario) {
  try {
    return JSON.parse(scenario.steps_json);
  } catch {
    return [];
  }
}

function formatDuration(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return null;
  const seconds = (new Date(finishedAt) - new Date(startedAt)) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  return `${seconds.toFixed(1)}s`;
}

function stepLabel(plannedStep, result) {
  // plannedStep (from the scenario's own steps_json, e.g. {action, selector,
  // value, expected}) has the action name and selector/value; result (the
  // executed RunStepOut, if this step has run yet) has only status/log_message.
  // Combine them: action name always shown, plus a short hint and, on
  // failure, the real error instead of a generic status word.
  const action = plannedStep?.action || "?";
  const hint = plannedStep?.selector || plannedStep?.expected || plannedStep?.value || null;
  const parts = [action];
  if (hint) parts.push(hint);
  if (result && result.status === "failed" && result.log_message) {
    parts.push(`— ${result.log_message}`);
  }
  return parts.join("  ");
}

export default function RunAccordion({ runs, scenarios }) {
  const [manualOpen, setManualOpen] = useState({});
  const [expandedSteps, setExpandedSteps] = useState({});

  const scenarioById = {};
  for (const s of scenarios) scenarioById[s.id] = s;

  const anyRunning = runs.some((r) => r.status === "running");
  const firstRunId = runs[0]?.id;

  function isOpen(run) {
    if (Object.prototype.hasOwnProperty.call(manualOpen, run.id)) {
      return manualOpen[run.id];
    }
    if (run.status === "running") return true;
    if (!anyRunning && run.id === firstRunId) return true;
    return false;
  }

  function toggleRun(runId) {
    setManualOpen((prev) => ({ ...prev, [runId]: !isOpenFor(runId) }));
  }

  function isOpenFor(runId) {
    const run = runs.find((r) => r.id === runId);
    return run ? isOpen(run) : false;
  }

  function toggleStep(key) {
    setExpandedSteps((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <ul className="space-y-2">
      {runs.map((run) => {
        const scenario = scenarioById[run.scenario_id];
        const plannedSteps = scenario ? parsedScenarioSteps(scenario) : [];
        const totalSteps = plannedSteps.length || run.steps.length;
        const completed = run.steps.length;
        const open = isOpen(run);
        const duration = formatDuration(run.started_at, run.finished_at);
        const statusLabel =
          run.status === "running" ? "running…" : run.status === "pending" ? "queued" : duration || run.status;

        return (
          <li key={run.id} className="rounded-md border border-border">
            <button
              type="button"
              onClick={() => toggleRun(run.id)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
            >
              <span className="w-4 text-muted-foreground">{RUN_ICON[run.status] || "○"}</span>
              <span className="flex-1">{scenario ? scenario.title : `Scenario ${run.scenario_id}`}</span>
              <span className="text-xs text-muted-foreground">
                {completed}/{totalSteps} {statusLabel}
              </span>
            </button>

            {open && (
              <ul className="space-y-1 border-t border-border px-3 py-2 pl-7">
                {Array.from({ length: totalSteps }).map((_, index) => {
                  const step = run.steps.find((s) => s.step_index === index);
                  const key = `${run.id}-${index}`;
                  const plannedStep = plannedSteps[index];
                  return (
                    <li key={key} className="text-sm">
                      <div className="flex items-center gap-2">
                        <span className="w-4 text-muted-foreground">
                          {step ? STEP_ICON[step.status] || "?" : "○"}
                        </span>
                        <span>{stepLabel(plannedStep, step)}</span>
                        {step && step.screenshot_path && (
                          <button
                            type="button"
                            onClick={() => toggleStep(key)}
                            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                          >
                            {expandedSteps[key] ? "hide screenshot" : "show screenshot"}
                          </button>
                        )}
                      </div>
                      {step && step.screenshot_path && expandedSteps[key] && (
                        <div className="mt-1 pl-6">
                          <Screenshot path={step.screenshot_path} stepIndex={index} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}
