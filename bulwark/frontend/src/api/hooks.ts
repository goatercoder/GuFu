/** react-query bindings for every endpoint the UI uses. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  ActivityEntry, AgentReportRow, AgentStatusItem, ApplyTemplateResponse, Asset, AuthMe,
  CatalogCheck, CatalogControlFull, CatalogResponse, CheckResult, ControlDetail, ControlListItem,
  CrmTemplateSummary, EnrollmentInfo, Evidence, Finding, Health, IngestResponse, Ok, Organization,
  PoamItem, PoamMilestone, Provider, Readiness, ResponsibilityRow, ScoreResult, ScoreSnapshot,
  SystemRecord,
} from "./types";

export const keys = {
  me: ["auth", "me"] as const,
  health: ["health"] as const,
  catalog: ["catalog"] as const,
  control: (id: string) => ["catalog", "control", id] as const,
  checks: ["catalog", "checks"] as const,
  crmTemplates: ["catalog", "crm-templates"] as const,
  organization: ["organization"] as const,
  systems: ["systems"] as const,
  system: (id: number) => ["systems", id] as const,
  controls: (id: number) => ["systems", id, "controls"] as const,
  controlDetail: (id: number, cid: string) => ["systems", id, "controls", cid] as const,
  score: (id: number) => ["systems", id, "score"] as const,
  history: (id: number) => ["systems", id, "score", "history"] as const,
  readiness: (id: number) => ["systems", id, "readiness"] as const,
  poam: (id: number) => ["systems", id, "poam"] as const,
  poamItem: (id: number) => ["poam", id] as const,
  evidence: (id: number) => ["systems", id, "evidence"] as const,
  assets: (id: number) => ["systems", id, "assets"] as const,
  assetChecks: (id: number) => ["assets", id, "checks"] as const,
  assetReports: (id: number) => ["assets", id, "reports"] as const,
  providers: ["providers"] as const,
  provider: (id: number) => ["providers", id] as const,
  matrix: (id: number) => ["providers", id, "matrix"] as const,
  enrollment: (id: number) => ["systems", id, "enrollment"] as const,
  agentStatus: (id: number) => ["systems", id, "agent-status"] as const,
  findings: (id: number) => ["systems", id, "findings"] as const,
  activity: ["admin", "activity"] as const,
};

// ------------------------------------------------------------------ auth
export const useMe = () =>
  useQuery({ queryKey: keys.me, queryFn: () => api.get<AuthMe>("/auth/me"), staleTime: 0 });

export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: () => api.get<Health>("/health") });

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => api.post<Ok>("/auth/login", { password }),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Ok>("/auth/logout"),
    onSuccess: () => qc.clear(),
  });
}

// ------------------------------------------------------------------ catalog
export const useCatalog = () =>
  useQuery({ queryKey: keys.catalog, queryFn: () => api.get<CatalogResponse>("/catalog"), staleTime: Infinity });

export const useCatalogControl = (controlId: string | undefined) =>
  useQuery({
    queryKey: keys.control(controlId ?? ""),
    queryFn: () => api.get<CatalogControlFull>(`/catalog/controls/${controlId}`),
    enabled: Boolean(controlId),
    staleTime: Infinity,
  });

export const useCatalogChecks = () =>
  useQuery({ queryKey: keys.checks, queryFn: () => api.get<CatalogCheck[]>("/catalog/checks"), staleTime: Infinity });

export const useCrmTemplates = () =>
  useQuery({ queryKey: keys.crmTemplates, queryFn: () => api.get<CrmTemplateSummary[]>("/catalog/crm-templates") });

// ------------------------------------------------------------------ organization & systems
export const useOrganization = () =>
  useQuery({
    queryKey: keys.organization,
    queryFn: () => api.get<Organization>("/organization"),
    retry: false,
  });

export function useSaveOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put<Organization>("/organization", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.organization });
      qc.invalidateQueries({ queryKey: keys.me });
    },
  });
}

export const useSystems = () =>
  useQuery({ queryKey: keys.systems, queryFn: () => api.get<SystemRecord[]>("/systems") });

export function useCreateSystem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<SystemRecord>("/systems", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.systems }),
  });
}

export function useUpdateSystem(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put<SystemRecord>(`/systems/${systemId}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.systems }),
  });
}

export function useDeleteSystem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (systemId: number) => api.del<Ok>(`/systems/${systemId}`),
    onSuccess: () => qc.invalidateQueries(),
  });
}

// ------------------------------------------------------------------ controls
export const useControls = (systemId: number | null) =>
  useQuery({
    queryKey: keys.controls(systemId ?? 0),
    queryFn: () => api.get<ControlListItem[]>(`/systems/${systemId}/controls`),
    enabled: systemId !== null,
  });

export const useControlDetail = (systemId: number | null, controlId: string | undefined) =>
  useQuery({
    queryKey: keys.controlDetail(systemId ?? 0, controlId ?? ""),
    queryFn: () => api.get<ControlDetail>(`/systems/${systemId}/controls/${controlId}`),
    enabled: systemId !== null && Boolean(controlId),
  });

export function useUpdateImplementation(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ controlId, body }: { controlId: string; body: Record<string, unknown> }) =>
      api.put<ControlDetail>(`/systems/${systemId}/controls/${controlId}`, body),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: keys.controls(systemId) });
      qc.invalidateQueries({ queryKey: keys.controlDetail(systemId, variables.controlId) });
      qc.invalidateQueries({ queryKey: keys.score(systemId) });
      qc.invalidateQueries({ queryKey: keys.readiness(systemId) });
      qc.invalidateQueries({ queryKey: keys.systems });
    },
  });
}

export function useUpdateObjectives(systemId: number, controlId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { objective_id: string; status: string; notes?: string | null }[]) =>
      api.put(`/systems/${systemId}/controls/${controlId}/objectives`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.controlDetail(systemId, controlId) });
      qc.invalidateQueries({ queryKey: keys.controls(systemId) });
      qc.invalidateQueries({ queryKey: keys.score(systemId) });
      qc.invalidateQueries({ queryKey: keys.readiness(systemId) });
    },
  });
}

// ------------------------------------------------------------------ scoring
export const useScore = (systemId: number | null) =>
  useQuery({
    queryKey: keys.score(systemId ?? 0),
    queryFn: () => api.get<ScoreResult>(`/systems/${systemId}/score`),
    enabled: systemId !== null,
  });

export const useScoreHistory = (systemId: number | null) =>
  useQuery({
    queryKey: keys.history(systemId ?? 0),
    queryFn: () => api.get<ScoreSnapshot[]>(`/systems/${systemId}/score/history`),
    enabled: systemId !== null,
  });

export const useReadiness = (systemId: number | null) =>
  useQuery({
    queryKey: keys.readiness(systemId ?? 0),
    queryFn: () => api.get<Readiness>(`/systems/${systemId}/readiness`),
    enabled: systemId !== null,
  });

export function useTakeSnapshot(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ScoreSnapshot>(`/systems/${systemId}/score/snapshot`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.history(systemId) }),
  });
}

// ------------------------------------------------------------------ POA&M
export const usePoam = (systemId: number | null, params?: Record<string, string>) =>
  useQuery({
    queryKey: [...keys.poam(systemId ?? 0), params ?? {}],
    queryFn: () => {
      const query = params && Object.keys(params).length
        ? `?${new URLSearchParams(params).toString()}`
        : "";
      return api.get<PoamItem[]>(`/systems/${systemId}/poam${query}`);
    },
    enabled: systemId !== null,
  });

export const usePoamItem = (itemId: number | undefined) =>
  useQuery({
    queryKey: keys.poamItem(itemId ?? 0),
    queryFn: () => api.get<PoamItem>(`/poam/${itemId}`),
    enabled: Boolean(itemId),
  });

function invalidatePoam(qc: ReturnType<typeof useQueryClient>, systemId: number, itemId?: number) {
  qc.invalidateQueries({ queryKey: keys.poam(systemId) });
  qc.invalidateQueries({ queryKey: keys.readiness(systemId) });
  qc.invalidateQueries({ queryKey: keys.controls(systemId) });
  if (itemId) qc.invalidateQueries({ queryKey: keys.poamItem(itemId) });
}

export function useCreatePoam(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<PoamItem>(`/systems/${systemId}/poam`, body),
    onSuccess: () => invalidatePoam(qc, systemId),
  });
}

export function useUpdatePoam(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: number; body: Record<string, unknown> }) =>
      api.put<PoamItem>(`/poam/${itemId}`, body),
    onSuccess: (_d, v) => invalidatePoam(qc, systemId, v.itemId),
  });
}

export function useTransitionPoam(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, status, note }: { itemId: number; status: string; note?: string }) =>
      api.post<PoamItem>(`/poam/${itemId}/transition`, { status, note }),
    onSuccess: (_d, v) => invalidatePoam(qc, systemId, v.itemId),
  });
}

export function useDeletePoam(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId: number) => api.del<Ok>(`/poam/${itemId}`),
    onSuccess: () => invalidatePoam(qc, systemId),
  });
}

export function useAddMilestone(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: number; body: Record<string, unknown> }) =>
      api.post<PoamMilestone>(`/poam/${itemId}/milestones`, body),
    onSuccess: (_d, v) => invalidatePoam(qc, systemId, v.itemId),
  });
}

export function useUpdateMilestone(systemId: number, itemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ milestoneId, body }: { milestoneId: number; body: Record<string, unknown> }) =>
      api.put<PoamMilestone>(`/milestones/${milestoneId}`, body),
    onSuccess: () => invalidatePoam(qc, systemId, itemId),
  });
}

export function useDeleteMilestone(systemId: number, itemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (milestoneId: number) => api.del<Ok>(`/milestones/${milestoneId}`),
    onSuccess: () => invalidatePoam(qc, systemId, itemId),
  });
}

// ------------------------------------------------------------------ evidence
export const useEvidence = (systemId: number | null, params?: Record<string, string>) =>
  useQuery({
    queryKey: [...keys.evidence(systemId ?? 0), params ?? {}],
    queryFn: () => {
      const query = params && Object.keys(params).length
        ? `?${new URLSearchParams(params).toString()}`
        : "";
      return api.get<Evidence[]>(`/systems/${systemId}/evidence${query}`);
    },
    enabled: systemId !== null,
  });

export function useUploadEvidence(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => api.upload<Evidence>(`/systems/${systemId}/evidence`, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.evidence(systemId) });
      qc.invalidateQueries({ queryKey: keys.readiness(systemId) });
      qc.invalidateQueries({ queryKey: keys.controls(systemId) });
    },
  });
}

export function useDeleteEvidence(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (evidenceId: number) => api.del<Ok>(`/evidence/${evidenceId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.evidence(systemId) });
      qc.invalidateQueries({ queryKey: keys.readiness(systemId) });
      qc.invalidateQueries({ queryKey: keys.controls(systemId) });
    },
  });
}

export function useLinkEvidence(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ evidenceId, controlId, objectiveId }:
      { evidenceId: number; controlId: string; objectiveId?: string | null }) =>
      api.post(`/evidence/${evidenceId}/links`, { control_id: controlId, objective_id: objectiveId ?? null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.evidence(systemId) });
      qc.invalidateQueries({ queryKey: keys.controls(systemId) });
      qc.invalidateQueries({ queryKey: ["systems", systemId, "controls"] });
    },
  });
}

// ------------------------------------------------------------------ assets
export const useAssets = (systemId: number | null) =>
  useQuery({
    queryKey: keys.assets(systemId ?? 0),
    queryFn: () => api.get<Asset[]>(`/systems/${systemId}/assets`),
    enabled: systemId !== null,
  });

export const useAssetChecks = (assetId: number | null) =>
  useQuery({
    queryKey: keys.assetChecks(assetId ?? 0),
    queryFn: () => api.get<CheckResult[]>(`/assets/${assetId}/checks`),
    enabled: assetId !== null,
  });

export const useAssetReports = (assetId: number | null) =>
  useQuery({
    queryKey: keys.assetReports(assetId ?? 0),
    queryFn: () => api.get<AgentReportRow[]>(`/assets/${assetId}/reports`),
    enabled: assetId !== null,
  });

function invalidateAssets(qc: ReturnType<typeof useQueryClient>, systemId: number) {
  qc.invalidateQueries({ queryKey: keys.assets(systemId) });
  qc.invalidateQueries({ queryKey: keys.readiness(systemId) });
  qc.invalidateQueries({ queryKey: keys.systems });
}

export function useCreateAsset(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Asset>(`/systems/${systemId}/assets`, body),
    onSuccess: () => invalidateAssets(qc, systemId),
  });
}

export function useUpdateAsset(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, body }: { assetId: number; body: Record<string, unknown> }) =>
      api.put<Asset>(`/assets/${assetId}`, body),
    onSuccess: () => invalidateAssets(qc, systemId),
  });
}

export function useDeleteAsset(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assetId: number) => api.del<Ok>(`/assets/${assetId}`),
    onSuccess: () => invalidateAssets(qc, systemId),
  });
}

// ------------------------------------------------------------------ providers
export const useProviders = () =>
  useQuery({ queryKey: keys.providers, queryFn: () => api.get<Provider[]>("/providers") });

export const useProvider = (providerId: number | undefined) =>
  useQuery({
    queryKey: keys.provider(providerId ?? 0),
    queryFn: () => api.get<Provider>(`/providers/${providerId}`),
    enabled: Boolean(providerId),
  });

export const useMatrix = (providerId: number | undefined) =>
  useQuery({
    queryKey: keys.matrix(providerId ?? 0),
    queryFn: () => api.get<ResponsibilityRow[]>(`/providers/${providerId}/matrix`),
    enabled: Boolean(providerId),
  });

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Provider>("/providers", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.providers }),
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ providerId, body }: { providerId: number; body: Record<string, unknown> }) =>
      api.put<Provider>(`/providers/${providerId}`, body),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: keys.providers });
      qc.invalidateQueries({ queryKey: keys.provider(v.providerId) });
    },
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerId: number) => api.del<Ok>(`/providers/${providerId}`),
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useSaveMatrix(providerId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rows: Record<string, unknown>[]) =>
      api.put<ResponsibilityRow[]>(`/providers/${providerId}/matrix`, rows),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.matrix(providerId) });
      qc.invalidateQueries({ queryKey: ["systems"] });
    },
  });
}

export function useApplyTemplate(providerId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (templateId: string) =>
      api.post<ApplyTemplateResponse>(`/providers/${providerId}/matrix/apply-template`, {
        template_id: templateId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.matrix(providerId) });
      qc.invalidateQueries({ queryKey: ["systems"] });
    },
  });
}

// ------------------------------------------------------------------ agents
export const useEnrollment = (systemId: number | null) =>
  useQuery({
    queryKey: keys.enrollment(systemId ?? 0),
    queryFn: () => api.get<EnrollmentInfo>(`/systems/${systemId}/enrollment`),
    enabled: systemId !== null,
  });

export const useAgentStatus = (systemId: number | null) =>
  useQuery({
    queryKey: keys.agentStatus(systemId ?? 0),
    queryFn: () => api.get<AgentStatusItem[]>(`/systems/${systemId}/agent-status`),
    enabled: systemId !== null,
  });

export const useFindings = (systemId: number | null) =>
  useQuery({
    queryKey: keys.findings(systemId ?? 0),
    queryFn: () => api.get<Finding[]>(`/systems/${systemId}/findings`),
    enabled: systemId !== null,
  });

export function useRotateKey(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<EnrollmentInfo>(`/systems/${systemId}/enrollment/rotate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.enrollment(systemId) }),
  });
}

export function useUploadReport(systemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) =>
      api.upload<IngestResponse>(`/systems/${systemId}/agent-reports/upload`, form),
    onSuccess: () => qc.invalidateQueries(),
  });
}

// ------------------------------------------------------------------ admin
export const useActivity = () =>
  useQuery({ queryKey: keys.activity, queryFn: () => api.get<ActivityEntry[]>("/admin/activity") });

export function useSeedDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Record<string, number | string>>("/admin/seed-demo"),
    onSuccess: () => qc.invalidateQueries(),
  });
}
