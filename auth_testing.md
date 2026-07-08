# Auth-Gated App Testing Playbook (saved from integration_playbook_expert_v2)

## Step 1: Create Test User & Session

```bash
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  role: 'admin',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Test Backend API
- GET /api/auth/me with Authorization: Bearer <session_token>
- Protected CRUD endpoints on /api/posts

## Step 3: Browser Testing
Set cookie session_token, navigate to /admin, verify no redirect to login.

## Checklist
- user_id is custom UUID (not MongoDB _id)
- All queries use projection {"_id": 0}
- Session user_id matches user's user_id
- Admin role check enforced on write operations

## Allow-list
This portfolio uses a single-owner allow-list — only emails in ADMIN_EMAILS env var can log in.
