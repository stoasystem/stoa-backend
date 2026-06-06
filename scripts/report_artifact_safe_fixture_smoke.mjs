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
  /<html/i,
  /raw_json/i,
  /raw_html/i,
]

function argValue(name) {
  const index = process.argv.indexOf(name)
  if (index === -1 || index + 1 >= process.argv.length) return null
  return process.argv[index + 1]
}

function hasArg(name) {
  return process.argv.includes(name)
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

function writeSummary(summary) {
  const outputPath = argValue('--output') || process.env.STOA_SAFE_FIXTURE_OUTPUT
  const text = JSON.stringify(summary, null, 2) + '\n'
  if (outputPath) writeFileSync(outputPath, text)
  console.log(text)
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
  const token = process.env.STOA_ADMIN_ACCESS_TOKEN
  if (token) return token
  const email = process.env.STOA_ADMIN_EMAIL
  const password = process.env.STOA_ADMIN_PASSWORD
  if (!email || !password) {
    throw new Error('Missing STOA_ADMIN_ACCESS_TOKEN or STOA_ADMIN_EMAIL/STOA_ADMIN_PASSWORD')
  }
  const loginResult = await call('POST', '/auth/login', null, { email, password })
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

function sanitizedRequest(result) {
  return {
    method: result.method,
    path: result.path,
    status: result.status,
    requestId: result.requestId,
    privateHits: result.privateHits,
  }
}

const config = {
  apiBase: argValue('--api-base') || process.env.STOA_API_BASE || 'https://api.stoaedu.ch',
  fixtureName: argValue('--fixture-name') || process.env.STOA_SAFE_FIXTURE_NAME,
  parentId: argValue('--parent-id') || process.env.STOA_SAFE_FIXTURE_PARENT_ID,
  studentId: argValue('--student-id') || process.env.STOA_SAFE_FIXTURE_STUDENT_ID,
  weekStart: argValue('--week-start') || process.env.STOA_SAFE_FIXTURE_WEEK_START,
  mutate: hasArg('--mutate-safe-fixture'),
}

const evidence = {
  timestamp: new Date().toISOString(),
  apiBase: config.apiBase,
  fixtureName: config.fixtureName || null,
  mutationAttempted: false,
  refused: false,
  refusalReasons: [],
  requests: [],
  artifactVersions: {},
  cleanupPassed: false,
  privacyPassed: false,
}

if (!config.mutate) evidence.refusalReasons.push('missing --mutate-safe-fixture')
if (!config.fixtureName) evidence.refusalReasons.push('missing fixture name')
if (!config.parentId || !config.studentId || !config.weekStart) {
  evidence.refusalReasons.push('missing fixture parent/student/week identifiers')
}

if (evidence.refusalReasons.length > 0) {
  evidence.refused = true
  writeSummary(evidence)
  process.exit(2)
}

try {
  const token = await login()
  const base = `/admin/reports/${encodeURIComponent(config.parentId)}/${encodeURIComponent(config.studentId)}/${encodeURIComponent(config.weekStart)}`
  const detail = await call('GET', `${base}/ops`, token)
  evidence.requests.push(sanitizedRequest(detail))
  if (detail.status !== 200) throw new Error(`Fixture report lookup failed with status ${detail.status}`)

  evidence.mutationAttempted = true
  const editPreview = await call('POST', `${base}/artifact-edit-previews`, token, {
    reason: `safe fixture ${config.fixtureName} artifact edit smoke`,
    proposed_fields: {
      summary: `Safe fixture ${config.fixtureName} smoke ${new Date().toISOString()}`,
    },
  })
  evidence.requests.push(sanitizedRequest(editPreview))
  if (editPreview.status !== 200) throw new Error(`Artifact edit preview failed with status ${editPreview.status}`)

  const editApply = await call(
    'POST',
    `${base}/artifact-edit-previews/${encodeURIComponent(editPreview.body.draft_id)}/apply`,
    token,
    { reason: `apply safe fixture ${config.fixtureName} artifact edit smoke` },
  )
  evidence.requests.push(sanitizedRequest(editApply))
  if (editApply.status !== 200) throw new Error(`Artifact edit apply failed with status ${editApply.status}`)
  evidence.artifactVersions.initial = editApply.body?.report?.previous_artifact_version_id || 'original'
  evidence.artifactVersions.edited = editApply.body?.report?.artifact_version_id || null

  const rollbackPreview = await call('POST', `${base}/artifact-rollback-previews`, token, {
    reason: `rollback safe fixture ${config.fixtureName} artifact edit smoke`,
  })
  evidence.requests.push(sanitizedRequest(rollbackPreview))
  if (rollbackPreview.status !== 200) {
    throw new Error(`Artifact rollback preview failed with status ${rollbackPreview.status}`)
  }

  const rollbackApply = await call(
    'POST',
    `${base}/artifact-rollback-previews/${encodeURIComponent(rollbackPreview.body.preview_id)}/apply`,
    token,
    { reason: `apply safe fixture ${config.fixtureName} artifact rollback smoke` },
  )
  evidence.requests.push(sanitizedRequest(rollbackApply))
  if (rollbackApply.status !== 200) {
    throw new Error(`Artifact rollback apply failed with status ${rollbackApply.status}`)
  }
  evidence.artifactVersions.restored = rollbackApply.body?.report?.artifact_version_id || null
  evidence.cleanupPassed = evidence.artifactVersions.restored === evidence.artifactVersions.initial
  evidence.privacyPassed = evidence.requests.every((item) => item.privateHits.length === 0)
  writeSummary(evidence)
} catch (error) {
  evidence.error = error instanceof Error ? error.message : String(error)
  evidence.privacyPassed = evidence.requests.every((item) => item.privateHits.length === 0)
  writeSummary(evidence)
  process.exit(1)
}
