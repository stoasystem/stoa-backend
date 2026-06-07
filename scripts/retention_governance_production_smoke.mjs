import { writeFileSync } from 'node:fs'

const denylist = [
  /weekly-reports\//i,
  /json_s3_key/i,
  /html_s3_key/i,
  /\bs3_key\b/i,
  /presignedUrl/i,
  /presigned_url/i,
  /https:\/\/s3/i,
  /accessToken/i,
  /id_token/i,
  /refresh_token/i,
  /raw_json/i,
  /raw_html/i,
  /<html/i,
  /cookie/i,
  /password/i,
  /secret/i,
]

function argValue(name) {
  const index = process.argv.indexOf(name)
  if (index === -1 || index + 1 >= process.argv.length) return null
  return process.argv[index + 1]
}

function privateHits(text) {
  return denylist.filter((pattern) => pattern.test(text)).map(String)
}

function requestId(response) {
  return (
    response.headers.get('x-amzn-requestid') ||
    response.headers.get('x-amz-apigw-id') ||
    response.headers.get('apigw-requestid') ||
    response.headers.get('x-request-id') ||
    response.headers.get('x-amzn-trace-id') ||
    null
  )
}

function parseSecret() {
  if (!process.env.STOA_ADMIN_SECRET_JSON) return {}
  try {
    const secret = JSON.parse(process.env.STOA_ADMIN_SECRET_JSON)
    return {
      email: secret.email || secret.username || secret.user || secret.admin_email,
      password: secret.password || secret.admin_password,
      accessToken: secret.accessToken || secret.access_token,
    }
  } catch {
    throw new Error('STOA_ADMIN_SECRET_JSON is not valid JSON')
  }
}

function authConfig() {
  const secret = parseSecret()
  return {
    accessToken: process.env.STOA_ADMIN_ACCESS_TOKEN || secret.accessToken || null,
    email: process.env.STOA_ADMIN_EMAIL || secret.email || null,
    password: process.env.STOA_ADMIN_PASSWORD || secret.password || null,
  }
}

function sanitizedRequest(result, safeBody = null) {
  return {
    method: result.method,
    path: result.path,
    status: result.status,
    requestId: result.requestId,
    privateHits: result.privateHits,
    ...(safeBody ? { body: safeBody } : {}),
  }
}

function safeGovernanceBody(body) {
  if (!body || typeof body !== 'object') return null
  return {
    schema_version: body.schema_version || null,
    immutable_storage: body.immutable_storage || null,
    retention_approval: body.retention_approval
      ? {
          policy_version: body.retention_approval.policy_version || null,
          approval_state: body.retention_approval.approval_state || null,
          approval_version: body.retention_approval.approval_version || null,
        }
      : null,
    legal_hold_reviews: body.legal_hold_reviews
      ? {
          scope_count: body.legal_hold_reviews.scope_count,
        }
      : null,
    privacy: body.privacy || null,
  }
}

function safeLegalHoldBody(body) {
  if (!body || typeof body !== 'object') return null
  return {
    schema_version: body.schema_version || null,
    scope_count: body.scope_count,
    item_statuses: Array.isArray(body.items)
      ? body.items.map((item) => ({
          scope: item.reference?.scope || null,
          status: item.status || null,
        }))
      : [],
    privacy: body.privacy || null,
  }
}

async function call(method, path, token, body) {
  const response = await fetch(`${config.apiBase}${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await response.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = null
  }
  return {
    method,
    path,
    status: response.status,
    requestId: requestId(response),
    privateHits: privateHits(text),
    body: json,
  }
}

async function login() {
  const auth = authConfig()
  if (auth.accessToken) return auth.accessToken
  if (!auth.email || !auth.password) {
    throw new Error('Missing STOA_ADMIN_ACCESS_TOKEN or STOA_ADMIN_EMAIL/STOA_ADMIN_PASSWORD')
  }
  const loginResult = await call('POST', '/auth/login', null, {
    email: auth.email,
    password: auth.password,
    role: 'admin',
  })
  evidence.requests.push({
    method: loginResult.method,
    path: loginResult.path,
    status: loginResult.status,
    requestId: loginResult.requestId,
    privateHits: [],
  })
  if (loginResult.status !== 200 || !loginResult.body?.accessToken) {
    throw new Error(`Admin login failed with status ${loginResult.status}`)
  }
  return loginResult.body.accessToken
}

function writeSummary(summary) {
  const outputPath = argValue('--output') || process.env.STOA_GOVERNANCE_SMOKE_OUTPUT
  const text = JSON.stringify(summary, null, 2) + '\n'
  if (outputPath) writeFileSync(outputPath, text)
  console.log(text)
}

const config = {
  apiBase: argValue('--api-base') || process.env.STOA_API_BASE || 'https://api.stoaedu.ch',
}

const evidence = {
  timestamp: new Date().toISOString(),
  apiBase: config.apiBase,
  mutationAttempted: false,
  requests: [],
  privacyPassed: false,
  authorizationPassed: false,
  statusPassed: false,
}

try {
  const health = await call('GET', '/health')
  evidence.requests.push(sanitizedRequest(health))

  const unauthGovernance = await call('POST', '/admin/reports/retention-governance/status', null, {
    policy_version: 'retention-policy-v1',
    references: [],
  })
  evidence.requests.push(sanitizedRequest(unauthGovernance))

  const token = await login()
  const governance = await call('POST', '/admin/reports/retention-governance/status', token, {
    policy_version: 'retention-policy-v1',
    references: [],
  })
  evidence.requests.push(sanitizedRequest(governance, safeGovernanceBody(governance.body)))

  const legalHold = await call('POST', '/admin/reports/legal-holds/status', token, {
    references: [
      {
        scope: 'release_evidence',
        release_evidence: {
          milestone: 'v2.9',
          phase: '88',
          check: 'production-read-only-smoke',
        },
      },
    ],
  })
  evidence.requests.push(sanitizedRequest(legalHold, safeLegalHoldBody(legalHold.body)))

  evidence.authorizationPassed = [401, 403].includes(unauthGovernance.status)
  evidence.statusPassed =
    health.status === 200 &&
    governance.status === 200 &&
    legalHold.status === 200
  evidence.privacyPassed = evidence.requests.every((item) => item.privateHits.length === 0)
  if (!evidence.authorizationPassed || !evidence.statusPassed || !evidence.privacyPassed) {
    throw new Error('Production governance smoke checks failed')
  }
  writeSummary(evidence)
} catch (error) {
  evidence.error = error instanceof Error ? error.message : String(error)
  evidence.privacyPassed = evidence.requests.every((item) => item.privateHits.length === 0)
  writeSummary(evidence)
  process.exit(1)
}
