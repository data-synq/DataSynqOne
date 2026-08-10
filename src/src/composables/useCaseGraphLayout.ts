import { computed, type ComputedRef, type Ref } from "vue";
import type { CaseLinkEdge, CaseSummary } from "../api/client";

export interface CaseGraphNode {
  trackingId: string;
  title: string;
  status: "open" | "closed";
  senderEmail: string | null;
  createdAt: string;
  lane: number;
  x: number;
  y: number;
}

export interface CaseGraphEdge {
  key: string;
  path: string;
  status: "proposed" | "confirmed";
  dependent: string;
  prerequisite: string;
  midX: number;
  midY: number;
}

export interface CaseGraphLayoutOptions {
  nodeWidth: number;
  nodeHeight: number;
  /** Abstand zwischen zwei Spuren (Zeilen). */
  laneGap: number;
  padding: number;
  /** Pixel je Kalendertag — die eigentliche Zeitachse, siehe useCaseGraphLayout. */
  pxPerDay: number;
  /** Mindestabstand zweier Knoten derselben Spur entlang der Zeitachse. Standard: nodeWidth + 54. */
  minTimeGap?: number;
}

/**
 * Git-graph-artiges Layout für Anliegen-Abhängigkeiten: die waagerechte Position
 * kommt direkt aus `created_at` (echte Zeitachse, kein Rang-Index, links früher
 * — rechts später), die Spur (Zeile) wird wie bei "git log --graph" vergeben,
 * damit eine Abhängigkeitskette so lange wie möglich in derselben Zeile bleibt.
 * Geteilt zwischen der großen Graph-Seite (CaseGraphView.vue) und dem
 * eingebetteten Mini-Graphen (CaseDependencyGraph.vue) — beide brauchen exakt
 * dieselbe Logik, nur mit unterschiedlichen Größenkonstanten.
 */
export function useCaseGraphLayout(
  cases: Ref<CaseSummary[]> | ComputedRef<CaseSummary[]>,
  edges: Ref<CaseLinkEdge[]> | ComputedRef<CaseLinkEdge[]>,
  options: CaseGraphLayoutOptions,
) {
  const NODE_W = options.nodeWidth;
  const NODE_H = options.nodeHeight;
  const LANE_GAP = options.laneGap;
  const PADDING = options.padding;
  const PX_PER_DAY = options.pxPerDay;
  const MIN_TIME_GAP = options.minTimeGap ?? NODE_W + 54;

  const layout = computed(() => {
    const byId = new Map(cases.value.map((c) => [c.tracking_id, c]));
    const prereqsOf = new Map<string, string[]>();
    const dependentsOf = new Map<string, string[]>();
    for (const e of edges.value) {
      (prereqsOf.get(e.dependent_tracking_id) ?? prereqsOf.set(e.dependent_tracking_id, []).get(e.dependent_tracking_id)!).push(
        e.prerequisite_tracking_id,
      );
      (dependentsOf.get(e.prerequisite_tracking_id) ?? dependentsOf.set(e.prerequisite_tracking_id, []).get(e.prerequisite_tracking_id)!).push(
        e.dependent_tracking_id,
      );
    }

    const sorted = [...cases.value].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );

    if (!sorted.length) {
      return { nodes: [] as CaseGraphNode[], laneCount: 0, minTime: 0, maxTime: 0 };
    }

    const minTime = new Date(sorted[0].created_at).getTime();
    const maxTime = new Date(sorted[sorted.length - 1].created_at).getTime();

    const idealX = (iso: string) => PADDING + ((new Date(iso).getTime() - minTime) / 86_400_000) * PX_PER_DAY;

    // Spurzuteilung im Stil von "git log --graph": eine Kette bleibt in ihrer
    // Spur, solange niemand sie übernommen hat; ein Blatt (keine Abhängigen)
    // gibt seine Spur sofort wieder frei, damit unabhängige Anliegen nicht
    // ständig neue Spuren aufreißen.
    const laneOccupant: (string | null)[] = [];
    const laneOfNode = new Map<string, number>();

    for (const c of sorted) {
      const prereqs = prereqsOf.get(c.tracking_id) ?? [];
      let chosenLane = -1;
      let bestTime = -Infinity;
      for (const p of prereqs) {
        const lane = laneOfNode.get(p);
        if (lane === undefined || laneOccupant[lane] !== p) continue;
        const pTime = new Date(byId.get(p)!.created_at).getTime();
        if (pTime > bestTime) {
          bestTime = pTime;
          chosenLane = lane;
        }
      }
      if (chosenLane === -1) {
        chosenLane = laneOccupant.findIndex((occupant) => occupant === null);
        if (chosenLane === -1) {
          chosenLane = laneOccupant.length;
          laneOccupant.push(null);
        }
      }
      laneOccupant[chosenLane] = c.tracking_id;
      laneOfNode.set(c.tracking_id, chosenLane);
      if (!(dependentsOf.get(c.tracking_id) ?? []).length) {
        laneOccupant[chosenLane] = null;
      }
    }

    // Kollisionsauflösung nur innerhalb derselben Spur: Knoten in anderen Spuren
    // überschneiden sich nie, egal wie nah sie zeitlich beieinander liegen — die
    // echte Zeitachse bleibt so weit wie möglich unangetastet.
    const byLane = new Map<number, string[]>();
    for (const [id, lane] of laneOfNode) {
      (byLane.get(lane) ?? byLane.set(lane, []).get(lane)!).push(id);
    }
    const finalX = new Map<string, number>();
    for (const ids of byLane.values()) {
      ids.sort((a, b) => idealX(byId.get(a)!.created_at) - idealX(byId.get(b)!.created_at));
      let prevX = -Infinity;
      for (const id of ids) {
        const x = Math.max(idealX(byId.get(id)!.created_at), prevX + MIN_TIME_GAP);
        finalX.set(id, x);
        prevX = x;
      }
    }

    const nodes: CaseGraphNode[] = sorted.map((c) => {
      const lane = laneOfNode.get(c.tracking_id)!;
      return {
        trackingId: c.tracking_id,
        title: c.title,
        status: c.status,
        senderEmail: c.sender_email,
        createdAt: c.created_at,
        lane,
        x: finalX.get(c.tracking_id)!,
        y: PADDING + lane * (NODE_H + LANE_GAP),
      };
    });

    return { nodes, laneCount: laneOccupant.length, minTime, maxTime };
  });

  const nodeById = computed(() => new Map(layout.value.nodes.map((n) => [n.trackingId, n])));

  const graphWidth = computed(() =>
    Math.max(NODE_W + PADDING * 2, ...layout.value.nodes.map((n) => n.x + NODE_W + PADDING), PADDING * 2),
  );
  const graphHeight = computed(() => Math.max(NODE_H + PADDING * 2, layout.value.laneCount * (NODE_H + LANE_GAP) + PADDING));

  const monthMarks = computed(() => {
    if (!layout.value.nodes.length) return [];
    const { minTime, maxTime } = layout.value;
    const marks: { x: number; label: string }[] = [];
    const cursor = new Date(minTime);
    cursor.setDate(1);
    cursor.setHours(0, 0, 0, 0);
    while (cursor.getTime() <= maxTime) {
      marks.push({
        x: PADDING + ((cursor.getTime() - minTime) / 86_400_000) * PX_PER_DAY,
        label: cursor.toLocaleDateString("de-DE", { month: "short", year: "numeric" }),
      });
      cursor.setMonth(cursor.getMonth() + 1);
    }
    return marks;
  });

  const edgeGeometries = computed<CaseGraphEdge[]>(() => {
    const result: CaseGraphEdge[] = [];
    for (const e of edges.value) {
      const from = nodeById.value.get(e.prerequisite_tracking_id);
      const to = nodeById.value.get(e.dependent_tracking_id);
      if (!from || !to) continue;
      const x1 = from.x + NODE_W;
      const y1 = from.y + NODE_H / 2;
      const x2 = to.x;
      const y2 = to.y + NODE_H / 2;
      const midX = (x1 + x2) / 2;
      result.push({
        key: `${e.dependent_tracking_id}-${e.prerequisite_tracking_id}`,
        path: `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`,
        status: e.status,
        dependent: e.dependent_tracking_id,
        prerequisite: e.prerequisite_tracking_id,
        midX,
        midY: (y1 + y2) / 2,
      });
    }
    return result;
  });

  return { NODE_W, NODE_H, layout, nodeById, graphWidth, graphHeight, monthMarks, edgeGeometries };
}
