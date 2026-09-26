// ═══════════════════════════════════════════════════════════════
// ByteToBite — Institutional facade (v4, offline mode)
// MODE = 'indexeddb' — works without any backend. Everything is
// stored locally in the browser. Perfect for the SIH demo.
//
// To use with FastAPI later, change MODE below to 'api'.
// ═══════════════════════════════════════════════════════════════

(function () {
    const isFile = typeof window !== 'undefined' && window.location.protocol === 'file:';
    const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

    const MODE = window.BYTETOBITE_MODE || (localStorage.getItem('bytetobite:mode') || (isFile ? 'indexeddb' : 'auto'));
    const API_BASE = window.BYTETOBITE_API || (
        (isLocal || isFile)
            ? 'http://localhost:8000'
            : (localStorage.getItem('bytetobite:api_base') || 'https://bytetobite-api.onrender.com')
    );
    const WS_BASE = window.BYTETOBITE_WS || (
        API_BASE.replace(/^http/, 'ws')
    );

    async function apiOr(apiFn, localFn) {
        if (MODE === 'api' || MODE === 'auto') {
            try {
                const res = await apiFn();
                if (res !== undefined && res !== null) return res;
            } catch (err) {
                console.warn('[InstitutionalAPI] Backend unreachable, using local DB:', err.message);
                return await localFn();
            }
        }
        return await localFn();
    }

    const DB_NAME = 'bytetobite_institutional';
    const DB_VERSION = 3;
    const STORES = {
        institutes: 'institutes', sessions: 'sessions', otp_requests: 'otp_requests',
        ngos: 'ngos', meal_plans: 'meal_plans', meal_preps: 'meal_preps',
        plate_tallies: 'plate_tallies', thermal_checks: 'thermal_checks',
        ngo_dispatches: 'ngo_dispatches', esg_ledger: 'esg_ledger',
    };

    let dbPromise = null;
    let ws = null;
    const wsSubscribers = new Set();
    let wsReconnectTimer = null;

    // ─────────────────────────────────────────────
    // INDEXEDDB
    // ─────────────────────────────────────────────
    function open() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = (e) => {
                const db = e.target.result;
                const ensure = (name, key, idx = []) => {
                    if (!db.objectStoreNames.contains(name)) {
                        const s = db.createObjectStore(name, { keyPath: key });
                        idx.forEach(([n, p, o]) => s.createIndex(n, p, o || {}));
                    }
                };
                ensure(STORES.institutes, 'id', [['code', 'code', { unique: true }], ['aishe_code', 'aishe_code'], ['admin_mobile', 'admin_mobile'], ['city', 'city']]);
                ensure(STORES.sessions, 'id', [['institute_id', 'institute_id'], ['expires_at', 'expires_at']]);
                ensure(STORES.otp_requests, 'id', [['mobile', 'mobile'], ['expires_at', 'expires_at']]);
                ensure(STORES.ngos, 'id', [['city', 'city'], ['verified', 'verified']]);
                ensure(STORES.meal_plans, 'id', [['institute_id', 'institute_id'], ['date', 'date'], ['status', 'status']]);
                ensure(STORES.meal_preps, 'id', [['institute_id', 'institute_id'], ['plan_id', 'plan_id']]);
                ensure(STORES.plate_tallies, 'id', [['prep_id', 'prep_id'], ['institute_id', 'institute_id']]);
                ensure(STORES.thermal_checks, 'id', [['prep_id', 'prep_id'], ['institute_id', 'institute_id']]);
                ensure(STORES.ngo_dispatches, 'id', [['institute_id', 'institute_id'], ['prep_id', 'prep_id'], ['plan_id', 'plan_id'], ['ngo_id', 'ngo_id'], ['created_at', 'created_at']]);
                ensure(STORES.esg_ledger, 'id', [['institute_id', 'institute_id'], ['dispatch_id', 'dispatch_id'], ['plan_id', 'plan_id'], ['created_at', 'created_at']]);
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
        return dbPromise;
    }
    const reqToPromise = (req) => new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); });
    async function tx(store, mode, fn) {
        const db = await open();
        return new Promise((res, rej) => {
            if (!db.objectStoreNames.contains(store)) return rej(new Error('Store missing: ' + store));
            const t = db.transaction(store, mode); const s = t.objectStore(store);
            let r; try { r = fn(s); } catch (e) { return rej(e); }
            t.oncomplete = () => res(r); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error);
        });
    }
    const ping = () => { try { localStorage.setItem('bytetobite:ping', Date.now().toString()); } catch { } };
    const broadcast = (n) => { window.dispatchEvent(new CustomEvent(n)); ping(); };
    const newId = (p) => p + '-' + Date.now().toString(36).toUpperCase() + '-' + Math.floor(Math.random() * 9999);
    function generateInstituteCode(name, city) {
        const n = (name || 'INST').replace(/[^A-Za-z]/g, '').toUpperCase().slice(0, 4) || 'INST';
        const c = (city || 'CITY').replace(/[^A-Za-z]/g, '').toUpperCase().slice(0, 4) || 'CITY';
        return `${n}-${c}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
    }

    // ─────────────────────────────────────────────
    // AGENTS (mirror of backend/agents.py)
    // ─────────────────────────────────────────────
    const DAY_WEIGHTS = { 0: -0.06, 1: 0, 2: 0, 3: 0.01, 4: 0.01, 5: 0.08, 6: 0.06 };
    const MEAL_BASE = { breakfast: 0.62, lunch: 1.0, dinner: 0.88 };
    const MENU_LIBRARY = [
        { name: 'Dal Tadka + Rice', category: 'staple', perishability: 0.35, kcal: 520, cost_inr: 22 },
        { name: 'Veg Pulao', category: 'staple', perishability: 0.40, kcal: 610, cost_inr: 28 },
        { name: 'Roti + Mixed Veg', category: 'staple', perishability: 0.30, kcal: 480, cost_inr: 20 },
        { name: 'Rajma Chawal', category: 'protein', perishability: 0.45, kcal: 640, cost_inr: 32 },
        { name: 'Chole Bhature', category: 'festive', perishability: 0.55, kcal: 780, cost_inr: 42 },
        { name: 'Paneer Butter Masala', category: 'protein', perishability: 0.60, kcal: 700, cost_inr: 55 },
        { name: 'Idli + Sambar', category: 'south', perishability: 0.25, kcal: 380, cost_inr: 18 },
        { name: 'Poha + Sev', category: 'breakfast', perishability: 0.20, kcal: 350, cost_inr: 15 },
        { name: 'Upma', category: 'breakfast', perishability: 0.22, kcal: 320, cost_inr: 14 },
        { name: 'Curd Rice', category: 'light', perishability: 0.65, kcal: 300, cost_inr: 16 },
        { name: 'Khichdi', category: 'light', perishability: 0.30, kcal: 420, cost_inr: 19 },
    ];
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

    const agents = {
        async forecast(institute_id, plan_date, meal_slot, opts = {}) {
            let historical = [];
            try {
                const plans = await api.getMealPlans(institute_id);
                historical = plans.filter(p => p.status === 'COMPLETED' && p.predicted_demand);
            } catch { }
            const base = historical.length ? Math.round(historical.reduce((s, p) => s + (p.predicted_demand || 0), 0) / historical.length) : 1000;
            const d = new Date(plan_date + 'T00:00:00');
            const dow = isNaN(d.getDay()) ? 1 : (d.getDay() === 0 ? 6 : d.getDay() - 1);
            const dayFactor = DAY_WEIGHTS[dow] ?? 0;
            const mealFactor = MEAL_BASE[meal_slot] ?? 1;
            const weatherFactor = opts.weather_factor ?? 0;
            const mult = (1 + dayFactor) * mealFactor * (1 + weatherFactor);
            const suggested = Math.max(50, Math.round(base * mult));
            const confidence = 0.82;
            const factors = [];
            if (dayFactor) factors.push({ label: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][dow], delta_pct: Math.round(dayFactor * 100) });
            if (!factors.length) factors.push({ label: 'Rolling 7-day avg', delta_pct: 0 });
            return { suggested_headcount: suggested, base_headcount: base, confidence, factors };
        },
        async wasteRisk(institute_id, plan_date, meal_slot, planned, menu) {
            const perishAvg = menu?.length ? menu.reduce((s, m) => s + (m.perishability ?? 0.4), 0) / menu.length : 0.4;
            return Math.round(clamp(perishAvg * 60 + 20, 0, 100));
        },
        suggestMenu(inventory, count = 4) {
            const inv = new Map((inventory || []).map(i => [(i.name || '').toLowerCase(), i]));
            return MENU_LIBRARY.map(item => {
                const have = inv.get(item.name.toLowerCase());
                const reuseScore = have ? 1 : 0;
                const costScore = 1 - clamp(item.cost_inr / 80, 0, 1);
                const perfScore = 1 - item.perishability;
                return { ...item, score: Math.round((reuseScore * 0.5 + costScore * 0.3 + perfScore * 0.2) * 100) / 100, reuse: !!have };
            }).sort((a, b) => b.score - a.score).slice(0, count);
        },
        anomaly(planned, suggested) {
            if (!suggested) return null;
            const delta = (planned - suggested) / suggested;
            if (Math.abs(delta) < 0.15) return null;
            return {
                severity: Math.abs(delta) > 0.35 ? 'high' : 'medium', delta_pct: Math.round(delta * 100),
                message: delta > 0 ? `Planning ${Math.round(delta * 100)}% above suggestion — surplus likely.`
                    : `Planning ${Math.abs(Math.round(delta * 100))}% below suggestion — shortage likely.`
            };
        },
    };

    // ═════════════════════════════════════════════
    // FACADE
    // ═════════════════════════════════════════════
    const api = {
        MODE,
        agents,

        async registerInstitute(inst) {
            return apiOr(
                async () => {
                    const saved = await fetchJson('/api/institutional/institutes', 'POST', inst);
                    try { const db = await open(); await tx(STORES.institutes, 'readwrite', s => s.put(saved)); } catch {}
                    broadcast('bytetobite:institutes-changed');
                    return saved;
                },
                async () => {
                    inst.id = inst.id || newId('INST');
                    inst.code = inst.code || generateInstituteCode(inst.name, inst.city);
                    inst.created_at = inst.created_at || Date.now();
                    inst.updated_at = Date.now();
                    await tx(STORES.institutes, 'readwrite', s => s.put(inst));
                    broadcast('bytetobite:institutes-changed');
                    return inst;
                }
            );
        },
        async getInstitute(id) {
            return apiOr(
                () => fetchJson(`/api/institutional/institutes/${encodeURIComponent(id)}`),
                async () => {
                    const db = await open(); const t = db.transaction(STORES.institutes, 'readonly');
                    return reqToPromise(t.objectStore(STORES.institutes).get(id));
                }
            );
        },
        async getInstituteByCode(code) {
            return apiOr(
                () => fetchJson(`/api/institutional/institutes?code=${encodeURIComponent(code)}`),
                async () => {
                    const db = await open(); const t = db.transaction(STORES.institutes, 'readonly');
                    return reqToPromise(t.objectStore(STORES.institutes).index('code').get(code));
                }
            );
        },
        async getInstituteByAishe(aishe) {
            return apiOr(
                () => fetchJson(`/api/institutional/institutes?aishe=${encodeURIComponent(aishe)}`),
                async () => {
                    const db = await open(); const t = db.transaction(STORES.institutes, 'readonly');
                    return reqToPromise(t.objectStore(STORES.institutes).index('aishe_code').get(aishe));
                }
            );
        },
        async getAllInstitutes() {
            return apiOr(
                () => fetchJson('/api/institutional/institutes'),
                async () => {
                    const db = await open(); const t = db.transaction(STORES.institutes, 'readonly');
                    return reqToPromise(t.objectStore(STORES.institutes).getAll());
                }
            );
        },
        async _generateCode(name, city) { return generateInstituteCode(name, city); },

        async saveSession(session) {
            if (MODE === 'api' || MODE === 'auto') {
                try {
                    await fetchJson('/api/institutional/session', 'POST', session);
                } catch (e) {
                    console.warn('[InstitutionalAPI] Backend session sync skipped:', e.message);
                }
            }
            session.id = session.id || newId('SESS');
            session.created_at = session.created_at || Date.now();
            session.expires_at = session.expires_at || (Date.now() + 7 * 24 * 3600 * 1000);
            try { await tx(STORES.sessions, 'readwrite', s => s.put(session)); } catch {}
            try {
                localStorage.setItem('bytetobite:institutional:session', JSON.stringify({
                    id: session.id, institute_id: session.institute_id, code: session.code,
                    name: session.name, role: session.role || null, at: session.created_at,
                }));
            } catch { }
            broadcast('bytetobite:session-changed');
            return session;
        },
        async setCurrentSession(s) { return api.saveSession(s); },
        async getCurrentSession() {
            try { const raw = localStorage.getItem('bytetobite:institutional:session'); return raw ? JSON.parse(raw) : null; }
            catch { return null; }
        },
        async clearSession() {
            try { localStorage.removeItem('bytetobite:institutional:session'); } catch { }
            broadcast('bytetobite:session-changed');
        },

        async createOtp(mobile) {
            if (MODE === 'api') return fetchJson('/api/institutional/otp', 'POST', { mobile });
            const otp = Math.floor(100000 + Math.random() * 900000).toString();
            const entry = { id: newId('OTP'), mobile, code: otp, expires_at: Date.now() + 600000, verified: false, created_at: Date.now() };
            await tx(STORES.otp_requests, 'readwrite', s => s.put(entry));
            return entry;
        },
        async verifyOtp(mobile, code) {
            if (MODE === 'api') { const r = await fetchJson('/api/institutional/otp/verify', 'POST', { mobile, code }); return !!(r && r.ok); }
            const db = await open(); const t = db.transaction(STORES.otp_requests, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.otp_requests).index('mobile').getAll(mobile));
            const match = all.filter(e => !e.verified && e.expires_at > Date.now()).sort((a, b) => b.created_at - a.created_at).find(e => e.code === code);
            if (!match) return false;
            match.verified = true;
            await tx(STORES.otp_requests, 'readwrite', s => s.put(match));
            return true;
        },

        async saveNGO(ngo) {
            if (MODE === 'api') return fetchJson('/api/institutional/ngos', 'POST', ngo);
            ngo.id = ngo.id || newId('NGO');
            ngo.created_at = ngo.created_at || Date.now();
            ngo.verified = ngo.verified !== false;
            await tx(STORES.ngos, 'readwrite', s => s.put(ngo));
            broadcast('bytetobite:ngos-changed');
            return ngo;
        },
        async getNGOs() {
            if (MODE === 'api') return fetchJson('/api/institutional/ngos');
            const db = await open(); const t = db.transaction(STORES.ngos, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.ngos).getAll());
            return all.filter(n => n.verified !== false);
        },
        async getNGO(id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/ngos/${encodeURIComponent(id)}`);
            const db = await open(); const t = db.transaction(STORES.ngos, 'readonly');
            return reqToPromise(t.objectStore(STORES.ngos).get(id));
        },
        async deleteNGO(id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/ngos/${id}`, 'DELETE');
            await tx(STORES.ngos, 'readwrite', s => s.delete(id));
            broadcast('bytetobite:ngos-changed');
        },

        async saveMealPlan(plan) {
            if (MODE === 'api') return fetchJson('/api/institutional/meal-plans', 'POST', plan);
            plan.id = plan.id || newId('PLAN');
            plan.created_at = plan.created_at || Date.now();
            plan.updated_at = Date.now();
            plan.status = plan.status || 'DRAFT';
            if (plan.status === 'PUBLISHED' && !plan.published_at) plan.published_at = Date.now();
            await tx(STORES.meal_plans, 'readwrite', s => s.put(plan));
            broadcast('bytetobite:meal-plans-changed');
            return plan;
        },
        async getMealPlans(institute_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-plans?institute=${encodeURIComponent(institute_id)}`);
            const db = await open(); const t = db.transaction(STORES.meal_plans, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.meal_plans).index('institute_id').getAll(institute_id));
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },
        async getMealPlan(id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-plans/${encodeURIComponent(id)}`);
            const db = await open(); const t = db.transaction(STORES.meal_plans, 'readonly');
            return reqToPromise(t.objectStore(STORES.meal_plans).get(id));
        },
        async getMealPlanFor(institute_id, plan_date, meal_slot) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-plans?institute=${encodeURIComponent(institute_id)}&date=${encodeURIComponent(plan_date)}&slot=${encodeURIComponent(meal_slot)}`);
            const plans = await api.getMealPlans(institute_id);
            return plans.find(p => p.date === plan_date && p.meal_slot === meal_slot) || null;
        },
        async publishMealPlan(id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-plans/${id}/publish`, 'POST');
            const plan = await api.getMealPlan(id);
            if (!plan) throw new Error('Not found');
            plan.status = 'PUBLISHED'; plan.published_at = Date.now(); plan.updated_at = Date.now();
            await tx(STORES.meal_plans, 'readwrite', s => s.put(plan));
            broadcast('bytetobite:meal-plans-changed');
            return plan;
        },
        async getMealPlanVariance(institute_id, days = 7) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-plans/variance?institute=${encodeURIComponent(institute_id)}&days=${days}`);
            return [];
        },

        async saveMealPrep(prep) {
            if (MODE === 'api') return fetchJson('/api/institutional/meal-preps', 'POST', prep);
            prep.id = prep.id || newId('PREP');
            prep.created_at = prep.created_at || Date.now();
            prep.updated_at = Date.now();
            await tx(STORES.meal_preps, 'readwrite', s => s.put(prep));
            broadcast('bytetobite:meal-preps-changed');
            return prep;
        },
        async getMealPreps(institute_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-preps?institute=${encodeURIComponent(institute_id)}`);
            const db = await open(); const t = db.transaction(STORES.meal_preps, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.meal_preps).index('institute_id').getAll(institute_id));
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },
        async getPrepByPlan(plan_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/meal-preps?plan=${encodeURIComponent(plan_id)}&latest=1`);
            const db = await open(); const t = db.transaction(STORES.meal_preps, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.meal_preps).index('plan_id').getAll(plan_id));
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0))[0] || null;
        },

        async savePlateTally(tally) {
            if (MODE === 'api') return fetchJson('/api/institutional/plate-tallies', 'POST', tally);
            tally.id = tally.id || newId('TALLY');
            tally.created_at = tally.created_at || Date.now();
            await tx(STORES.plate_tallies, 'readwrite', s => s.put(tally));
            broadcast('bytetobite:tallies-changed');
            return tally;
        },
        async getLatestTally(prep_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/plate-tallies?prep=${encodeURIComponent(prep_id)}&latest=1`);
            const db = await open(); const t = db.transaction(STORES.plate_tallies, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.plate_tallies).index('prep_id').getAll(prep_id));
            if (!all.length) return null;
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0))[0];
        },
        async getTalliesByInstitute(institute_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/plate-tallies?institute=${encodeURIComponent(institute_id)}`);
            const db = await open(); const t = db.transaction(STORES.plate_tallies, 'readonly');
            return reqToPromise(t.objectStore(STORES.plate_tallies).index('institute_id').getAll(institute_id));
        },

        async saveThermalCheck(check) {
            if (MODE === 'api') return fetchJson('/api/institutional/thermal-checks', 'POST', check);
            check.id = check.id || newId('THERM');
            check.created_at = check.created_at || Date.now();
            await tx(STORES.thermal_checks, 'readwrite', s => s.put(check));
            broadcast('bytetobite:thermal-changed');
            return check;
        },
        async getLatestThermal(prep_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/thermal-checks?prep=${encodeURIComponent(prep_id)}&latest=1`);
            const db = await open(); const t = db.transaction(STORES.thermal_checks, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.thermal_checks).index('prep_id').getAll(prep_id));
            if (!all.length) return null;
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0))[0];
        },

        async saveDispatch(dispatch) {
            if (MODE === 'api') return fetchJson('/api/institutional/dispatches', 'POST', dispatch);
            dispatch.id = dispatch.id || newId('DISP');
            dispatch.dispatch_code = dispatch.dispatch_code || ('D-' + Date.now().toString(36).toUpperCase());
            dispatch.created_at = dispatch.created_at || Date.now();
            await tx(STORES.ngo_dispatches, 'readwrite', s => s.put(dispatch));
            broadcast('bytetobite:dispatches-changed');
            return dispatch;
        },
        async getDispatches(institute_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/dispatches?institute=${encodeURIComponent(institute_id)}`);
            const db = await open(); const t = db.transaction(STORES.ngo_dispatches, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.ngo_dispatches).index('institute_id').getAll(institute_id));
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },
        async getDispatch(id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/dispatches/${encodeURIComponent(id)}`);
            const db = await open(); const t = db.transaction(STORES.ngo_dispatches, 'readonly');
            return reqToPromise(t.objectStore(STORES.ngo_dispatches).get(id));
        },

        async saveEsgEntry(entry) {
            if (MODE === 'api') return fetchJson('/api/institutional/esg-ledger', 'POST', entry);
            entry.id = entry.id || newId('ESG');
            entry.created_at = entry.created_at || Date.now();
            await tx(STORES.esg_ledger, 'readwrite', s => s.put(entry));
            broadcast('bytetobite:esg-changed');
            return entry;
        },
        async getEsgEntries(institute_id) {
            if (MODE === 'api') return fetchJson(`/api/institutional/esg-ledger?institute=${encodeURIComponent(institute_id)}`);
            const db = await open(); const t = db.transaction(STORES.esg_ledger, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.esg_ledger).index('institute_id').getAll(institute_id));
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },

        async getInstituteSummary(institute_id) {
            return apiOr(
                () => fetchJson(`/api/institutional/institutes/${encodeURIComponent(institute_id)}/summary`),
                async () => {
                    const [plans, preps, dispatches, esg] = await Promise.all([
                        api.getMealPlans(institute_id), api.getMealPreps(institute_id),
                        api.getDispatches(institute_id), api.getEsgEntries(institute_id),
                    ]);
                    return {
                        total_plans: plans.length, total_preps: preps.length, total_dispatches: dispatches.length,
                        total_meals_rescued: dispatches.reduce((s, d) => s + (d.meals_sent || 0), 0),
                        total_co2e_saved: esg.reduce((s, e) => s + (e.co2e_kg || 0), 0),
                        total_water_saved: esg.reduce((s, e) => s + (e.water_l || 0), 0),
                        total_value_saved: esg.reduce((s, e) => s + (e.cost_inr || 0), 0),
                        last_activity: dispatches[0]?.created_at || plans[0]?.created_at || null,
                    };
                }
            );
        },

        subscribe(callback) {
            if (MODE === 'api') {
                wsSubscribers.add(callback); if (!ws) openWs();
                return () => wsSubscribers.delete(callback);
            }
            const events = [
                'bytetobite:institutes-changed', 'bytetobite:session-changed', 'bytetobite:ngos-changed',
                'bytetobite:meal-plans-changed', 'bytetobite:meal-preps-changed', 'bytetobite:tallies-changed',
                'bytetobite:thermal-changed', 'bytetobite:dispatches-changed', 'bytetobite:esg-changed', 'storage',
            ];
            const handler = () => callback();
            events.forEach(e => window.addEventListener(e, handler));
            return () => events.forEach(e => window.removeEventListener(e, handler));
        },

        async _seedDemoFor(institute_id) {
            if (MODE === 'api' || MODE === 'auto') {
                try {
                    return await fetchJson(`/api/institutional/institutes/${encodeURIComponent(institute_id)}/seed`, 'POST');
                } catch (e) {
                    console.warn('[InstitutionalAPI] Backend seed unavailable, seeding locally:', e.message);
                }
            }
            const now = Date.now();
            const dayMs = 24 * 3600 * 1000;

            const ngoSeeds = [
                { id: 'NGO-DEMO-1', name: 'Aahar Center Khandagiri', contact: 'Rajesh Mohapatra', phone: '+91 94370 12345', email: 'aahar.khandagiri@odisha.gov.in', coords: { lat: 20.2612, lng: 85.7895 }, distanceKm: 2.8, capacity: 250, baseEtaMin: 9, city: 'Bhubaneswar', verified: true },
                { id: 'NGO-DEMO-2', name: 'Mission Ashra Shelter', contact: 'Dr. Sunita Nayak', phone: '+91 98610 54321', email: 'dispatch@missionashra.org', coords: { lat: 20.2310, lng: 85.7920 }, distanceKm: 4.6, capacity: 180, baseEtaMin: 14, city: 'Bhubaneswar', verified: true },
                { id: 'NGO-DEMO-3', name: 'Jeevan Jyoti Destitute Home', contact: 'Sister Teresa', phone: '+91 94380 98765', email: 'contact@jeevanjyoti-odisha.org', coords: { lat: 20.2850, lng: 85.8150 }, distanceKm: 8.2, capacity: 120, baseEtaMin: 22, city: 'Bhubaneswar', verified: true },
                { id: 'NGO-DEMO-4', name: 'Bhubaneswar Urban Food Bank', contact: 'Alok Jena', phone: '+91 99370 11223', email: 'ops@bbsrfoodbank.org', coords: { lat: 20.2980, lng: 85.8450 }, distanceKm: 13.5, capacity: 500, baseEtaMin: 36, city: 'Bhubaneswar', verified: true },
            ];
            for (const n of ngoSeeds) await api.saveNGO(n);

            const meals = ['breakfast', 'lunch', 'dinner'];
            const menuPool = [
                ['Dal Tadka + Rice', 'Roti + Mixed Veg'],
                ['Veg Pulao', 'Curd Rice'],
                ['Chole Bhature', 'Kheer'],
            ];

            for (let i = 1; i <= 7; i++) {
                const d = new Date(now - i * dayMs);
                const dateStr = d.toISOString().split('T')[0];
                const slot = meals[i % 3];
                const baseHead = 1150 + Math.round((Math.random() - 0.5) * 120);
                const variance = Math.round((Math.random() * 14 - 4));

                const plan = await api.saveMealPlan({
                    institute_id, date: dateStr, meal_slot: slot,
                    predicted_demand: baseHead,
                    prepared_count: baseHead + Math.round(Math.random() * 30),
                    menu_items: menuPool[i % menuPool.length].map(n => ({ name: n, perishability: 0.4 })),
                    status: 'COMPLETED',
                    expected_waste_kg: Math.round(baseHead * 0.12 * 0.35),
                    waste_risk_score: 30 + Math.round(Math.random() * 30),
                    agent_suggested: true, agent_headcount: baseHead, variance_pct: variance,
                    dispatch_ready: true, dispatch_ready_at: now - i * dayMs - 2 * 3600 * 1000,
                });

                const prep = await api.saveMealPrep({
                    institute_id, plan_id: plan.id,
                    prepared_count: plan.prepared_count,
                    chef_verified_at: now - i * dayMs - 3 * 3600 * 1000,
                    notes: 'Demo prep',
                });

                const served = Math.max(0, plan.prepared_count - Math.round(plan.prepared_count * (0.04 + Math.random() * 0.10)));
                await api.savePlateTally({ prep_id: prep.id, institute_id, served_count: served });
                await api.saveThermalCheck({
                    prep_id: prep.id, institute_id, temp_c: 62 + Math.round(Math.random() * 6),
                    state: 'FRESH_WARM', hold_minutes: 20 + Math.round(Math.random() * 20),
                    remaining_minutes: 70 - Math.round(Math.random() * 20),
                    freshness_index: 0.75 + Math.random() * 0.2, ready_for_dispatch: true,
                });

                const surplus = Math.max(0, plan.prepared_count - served);
                if (surplus > 20) {
                    const ngo = ngoSeeds[i % ngoSeeds.length];
                    const dispatch = await api.saveDispatch({
                        institute_id, prep_id: prep.id, plan_id: plan.id,
                        ngo_id: ngo.id, ngo_name: ngo.name,
                        ngo_distance_km: ngo.distanceKm,
                        ngo_contact: ngo.contact, ngo_phone: ngo.phone, ngo_email: ngo.email,
                        meals_sent: surplus, eta_minutes: ngo.baseEtaMin,
                        custody_officer: 'Mess Lead',
                        verified_at: now - i * dayMs - 2 * 3600 * 1000,
                    });
                    await api.saveEsgEntry({
                        institute_id, dispatch_id: dispatch.id, plan_id: plan.id,
                        meals_rescued: surplus,
                        co2e_kg: +(surplus * 1.05).toFixed(2),
                        water_l: Math.round(surplus * 180),
                        cost_inr: Math.round(surplus * 45),
                    });
                }
            }

            const tmr = new Date(now + dayMs).toISOString().split('T')[0];
            await api.saveMealPlan({ institute_id, date: tmr, meal_slot: 'lunch', predicted_demand: null, menu_items: [], status: 'DRAFT' });

            ['institutes', 'ngos', 'meal-plans', 'meal-preps', 'tallies', 'thermal', 'dispatches', 'esg']
                .forEach(s => broadcast(`bytetobite:${s}-changed`));
        },

        async _resetAll() {
            const db = await open();
            await Promise.all(Object.values(STORES).map(n => {
                if (!db.objectStoreNames.contains(n)) return Promise.resolve();
                return tx(n, 'readwrite', s => s.clear());
            }));
        },
    };

    // ─────────────────────────────────────────────
    // API helper (used when MODE = 'api')
    // ─────────────────────────────────────────────
    function authHeader() {
        try { const r = localStorage.getItem('bytetobite:institutional:jwt'); return r ? { Authorization: `Bearer ${r}` } : {}; } catch { return {}; }
    }
    async function fetchJson(path, method = 'GET', body) {
        const res = await fetch(`${API_BASE}${path}`, {
            method,
            headers: { 'Content-Type': 'application/json', ...authHeader() },
            body: body != null ? JSON.stringify(body) : undefined,
        });
        if (!res.ok) { let d = res.statusText; try { const j = await res.json(); d = j.detail || d; } catch { } throw new Error(`${res.status} ${d}`); }
        if (res.status === 204) return null;
        return res.json();
    }

    function openWs() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
        try { ws = new WebSocket(`${WS_BASE}/ws/institutional`); } catch { scheduleReconnect(); return; }
        ws.onmessage = (e) => {
            try {
                const p = JSON.parse(e.data); const t = p.type || '';
                if (t.endsWith('-changed')) { broadcast(`bytetobite:${t}`); wsSubscribers.forEach(cb => { try { cb(`bytetobite:${t}`); } catch { } }); }
            } catch { }
        };
        ws.onclose = scheduleReconnect;
        ws.onerror = () => { try { ws.close(); } catch { } };
    }
    function scheduleReconnect() {
        if (wsReconnectTimer) return;
        wsReconnectTimer = setTimeout(() => { wsReconnectTimer = null; if (wsSubscribers.size) openWs(); }, 3000);
    }

    window.InstitutionalAPI = api;
})();