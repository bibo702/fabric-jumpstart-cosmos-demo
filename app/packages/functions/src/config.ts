const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function getConfig() {
  const env = process.env;
  const workspace = env.PIM_WORKSPACE_ID ?? '';
  const item = env.PIM_UDF_ITEM_ID ?? '';
  const tenant = env.PIM_CALLER_TENANT_ID ?? '';
  const audience = env.PIM_CALLER_AUDIENCE ?? '';
  const subject = env.PIM_CALLER_SUBJECT ?? '';
  const endpoint = new URL(env.PIM_RAYFIN_ENDPOINT ?? 'https://invalid.invalid');
  if (![workspace, item, tenant, audience].every((value) => uuid.test(value))
    || endpoint.protocol !== 'https:' || endpoint.username || endpoint.password
    || endpoint.search || endpoint.hash || !endpoint.hostname.endsWith('.pbidedicated.windows.net')
    || !/^\/webapi\/capacities\/[0-9a-f-]+\/workloads\/BaaS\/BaaSService\/automatic\/v1\/workspaces\/[0-9a-f-]+\/appbackends\/[0-9a-f-]+\/?$/i.test(endpoint.pathname)
    || !subject.startsWith('/eid1/c/pub/t/') || subject.length > 2_048
    || !subject.includes(`/workspaces/${endpoint.pathname.split('/workspaces/')[1].split('/')[0]}/projects/`)
    || !subject.includes(`/projects/${endpoint.pathname.split('/appbackends/')[1].replace(/\/$/, '')}/users/`)
    || !uuid.test(subject.split('/users/')[1] ?? '')) {
    throw new Error('Missing or invalid explicit PIM configuration.');
  }
  return {
    baseUrl: `https://api.fabric.microsoft.com/v1/workspaces/${workspace}/userDataFunctions/${item}/functions`,
    endpoint: endpoint.href.replace(/\/+$/, ''),
    policy: { tenant, audience, subject, issuer: `https://sts.windows.net/${tenant}/` },
  };
}

export function configured(): boolean {
  try { getConfig(); return true; } catch { return false; }
}

export function validEndpoint(baseUrl: string): boolean {
  try { return baseUrl.replace(/\/+$/, '') === getConfig().endpoint; } catch { return false; }
}
