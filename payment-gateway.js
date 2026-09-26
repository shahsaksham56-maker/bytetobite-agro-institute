// ═══════════════════════════════════════════════════════════════
// ByteToBite — Universal Payment Gateway (v4)
//
// Works on every agro page (page1–page6) AND every institutional page.
// Talks to /api/payments/create-order and /api/payments/verify on the backend.
//
// MODE:
//   'razorpay'  → real Razorpay Checkout (live or test keys from .env)
//   'demo'      → fully offline modal (no network, no keys needed)
//
// Usage:
//   PaymentGateway.open({
//     amount: 1234.50,                       // rupees
//     purpose: 'Escrow advance · LOT-8291',
//     metadata: { lotId: 'LOT-8291', milestone: 'ADVANCE_30' },
//     prefill: { name: 'Ravi', contact: '9876543210', email: 'r@a.in' },
//     onSuccess: (payment) => { ... },
//     onCancel: () => { ... },
//     onError: (err) => { ... },
//   });
// ═══════════════════════════════════════════════════════════════

(function () {
    'use strict';

    const MODE = window.BYTETOBITE_PAYMENT_MODE || (localStorage.getItem('bytetobite:payment_mode') || 'razorpay');
    const API_BASE = window.BYTETOBITE_API || (
        (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'))
            ? 'http://localhost:8000'
            : (localStorage.getItem('bytetobite:api_base') || 'https://bytetobite-api.onrender.com')
    );
    const BRAND_COLOR = '#FF724C';
    const CURRENCY = 'INR';

    let modalEl = null;
    let razorpayScriptPromise = null;
    let lastSession = null;

    // ─────────────────────────────────────────────
    // HELPERS
    // ─────────────────────────────────────────────
    function money(n) {
        return '₹' + Number(n || 0).toLocaleString('en-IN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function validateSession(session) {
        if (!session || typeof session !== 'object') throw new Error('PaymentGateway.open requires a session object');
        if (typeof session.amount !== 'number' || !isFinite(session.amount) || session.amount < 1) {
            throw new Error('PaymentGateway.open requires { amount: number >= 1 }');
        }
    }

    // ─────────────────────────────────────────────
    // RAZORPAY SCRIPT LOADER
    // ─────────────────────────────────────────────
    function ensureRazorpayScript() {
        if (razorpayScriptPromise) return razorpayScriptPromise;
        razorpayScriptPromise = new Promise((resolve, reject) => {
            if (typeof window.Razorpay !== 'undefined') return resolve();
            const existing = document.querySelector('script[data-btb="razorpay"]');
            if (existing) {
                existing.addEventListener('load', () => resolve());
                existing.addEventListener('error', () => reject(new Error('Razorpay script failed')));
                return;
            }
            const s = document.createElement('script');
            s.src = 'https://checkout.razorpay.com/v1/checkout.js';
            s.async = true;
            s.dataset.btb = 'razorpay';
            s.onload = () => resolve();
            s.onerror = () => reject(new Error('Razorpay script failed'));
            document.head.appendChild(s);
        });
        return razorpayScriptPromise;
    }

    // ─────────────────────────────────────────────
    // BACKEND CALLS
    // ─────────────────────────────────────────────
    async function createOrderOnServer(session) {
        const res = await fetch(`${API_BASE}/api/payments/create-order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: session.amount,
                currency: session.currency || CURRENCY,
                receipt: session.receipt || ('btb_' + Date.now()),
                notes: session.metadata || {},
            }),
        });
        if (!res.ok) {
            let detail = res.statusText;
            try { const j = await res.json(); detail = j.detail || detail; } catch { }
            throw new Error(`Order create failed: ${res.status} ${detail}`);
        }
        return res.json();
    }

    async function verifyOnServer(response) {
        const res = await fetch(`${API_BASE}/api/payments/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
            }),
        });
        if (!res.ok) return { ok: false };
        return res.json();
    }

    async function persistPayment(payment) {
        try {
            const api = window.ByteToBiteAPI || window.InstitutionalAPI;
            if (api && typeof api.savePayment === 'function') {
                await api.savePayment(payment);
            }
        } catch (e) {
            console.warn('[PaymentGateway] savePayment failed', e);
        }
    }

    // ─────────────────────────────────────────────
    // DEMO MODAL (offline fallback)
    // ─────────────────────────────────────────────
    function ensureModal() {
        if (modalEl) return modalEl;
        modalEl = document.createElement('div');
        modalEl.id = 'btb-payment-modal';
        modalEl.style.cssText =
            'position:fixed;inset:0;z-index:9999;display:none;' +
            'align-items:center;justify-content:center;padding:16px;' +
            'background:rgba(0,0,0,0.72);backdrop-filter:blur(8px);' +
            'font-family:"Inter",system-ui,sans-serif;';
        document.body.appendChild(modalEl);
        return modalEl;
    }

    function closeModal() {
        if (modalEl) {
            modalEl.style.display = 'none';
            modalEl.innerHTML = '';
        }
    }

    function renderDemoModal(session) {
        const modal = ensureModal();
        const amountStr = money(session.amount);

        modal.innerHTML = `
            <div style="background:#0B111E;border:1px solid rgba(180,205,255,0.2);border-radius:24px;padding:32px;width:100%;max-width:420px;color:#F7F5F2;box-shadow:0 24px 60px rgba(0,0,0,0.5);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
                    <div style="font-size:13px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.5);">Payment</div>
                    <button id="btb-pay-close" style="background:rgba(255,255,255,0.06);border:none;color:rgba(255,255,255,0.6);width:32px;height:32px;border-radius:999px;cursor:pointer;font-size:16px;">✕</button>
                </div>

                <div style="margin-bottom:24px;">
                    <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-bottom:6px;">Purpose</div>
                    <div style="font-size:15px;font-weight:500;">${escapeHtml(session.purpose || 'Payment')}</div>
                </div>

                <div style="background:rgba(94,234,212,0.06);border:1px solid rgba(94,234,212,0.2);border-radius:14px;padding:18px;margin-bottom:24px;">
                    <div style="display:flex;justify-content:space-between;align-items:baseline;">
                        <span style="font-size:12px;color:rgba(255,255,255,0.6);">Amount due</span>
                        <span style="font-size:32px;font-weight:700;color:#5EEAD4;font-family:'JetBrains Mono',monospace;">${amountStr}</span>
                    </div>
                </div>

                <div style="display:flex;gap:8px;margin-bottom:24px;">
                    <div id="btb-pay-upi" style="flex:1;text-align:center;padding:12px;border-radius:12px;border:1px solid rgba(94,234,212,0.4);background:rgba(94,234,212,0.08);cursor:pointer;font-size:13px;font-weight:600;color:#5EEAD4;">UPI</div>
                    <div id="btb-pay-card" style="flex:1;text-align:center;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.04);cursor:pointer;font-size:13px;color:rgba(255,255,255,0.6);">Card</div>
                    <div id="btb-pay-net" style="flex:1;text-align:center;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.04);cursor:pointer;font-size:13px;color:rgba(255,255,255,0.6);">NetBanking</div>
                </div>

                <button id="btb-pay-submit" style="width:100%;padding:16px;border-radius:14px;border:none;background:linear-gradient(145deg,#FF8159,#FF5C30);color:#fff;font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 8px 24px rgba(255,92,48,0.35);">
                    Pay ${amountStr}
                </button>

                <div style="margin-top:12px;font-size:10.5px;color:rgba(255,255,255,0.35);text-align:center;font-family:'JetBrains Mono',monospace;">
                    Demo mode · no real payment
                </div>
            </div>
        `;
        modal.style.display = 'flex';

        const tabs = ['upi', 'card', 'net'];
        tabs.forEach(t => {
            const el = modal.querySelector('#btb-pay-' + t);
            if (!el) return;
            el.addEventListener('click', () => {
                tabs.forEach(x => {
                    const e = modal.querySelector('#btb-pay-' + x);
                    if (!e) return;
                    e.style.border = '1px solid rgba(255,255,255,0.15)';
                    e.style.background = 'rgba(255,255,255,0.04)';
                    e.style.color = 'rgba(255,255,255,0.6)';
                    e.style.fontWeight = '400';
                });
                el.style.border = '1px solid rgba(94,234,212,0.4)';
                el.style.background = 'rgba(94,234,212,0.08)';
                el.style.color = '#5EEAD4';
                el.style.fontWeight = '600';
            });
        });

        modal.querySelector('#btb-pay-close').addEventListener('click', () => {
            closeModal();
            if (session.onCancel) session.onCancel();
        });

        modal.querySelector('#btb-pay-submit').addEventListener('click', async () => {
            const btn = modal.querySelector('#btb-pay-submit');
            btn.disabled = true;
            btn.textContent = 'Processing…';
            btn.style.opacity = '0.7';

            await new Promise(r => setTimeout(r, 1600));

            const payment = {
                id: 'pay_DEMO_' + Date.now().toString(36).toUpperCase(),
                payment_id: 'pay_DEMO_' + Date.now().toString(36).toUpperCase(),
                amount: session.amount,
                currency: session.currency || CURRENCY,
                purpose: session.purpose,
                metadata: session.metadata || {},
                status: 'captured',
                mode: 'demo',
                created_at: Date.now(),
            };

            await persistPayment(payment);
            closeModal();
            if (session.onSuccess) session.onSuccess(payment);
        });
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    // ─────────────────────────────────────────────
    // RAZORPAY LIVE MODE
    // ─────────────────────────────────────────────
    async function renderRazorpay(session) {
        try {
            await ensureRazorpayScript();
        } catch (err) {
            console.error('[PaymentGateway] Razorpay script missing', err);
            if (session.onError) session.onError(err);
            return;
        }

        let order;
        try {
            order = await createOrderOnServer(session);
        } catch (err) {
            console.error('[PaymentGateway] Order create failed', err);
            if (session.onError) session.onError(err);
            return;
        }

        const options = {
            key: order.key_id,
            amount: order.amount,
            currency: order.currency || CURRENCY,
            name: 'ByteToBite',
            description: session.purpose || 'Payment',
            order_id: order.id,
            prefill: session.prefill || {},
            notes: session.metadata || {},
            theme: { color: BRAND_COLOR },
            handler: async function (response) {
                try {
                    const verified = await verifyOnServer(response);
                    const payment = {
                        id: response.razorpay_payment_id,
                        payment_id: response.razorpay_payment_id,
                        order_id: response.razorpay_order_id,
                        signature: response.razorpay_signature,
                        amount: session.amount,
                        currency: session.currency || CURRENCY,
                        purpose: session.purpose,
                        metadata: session.metadata || {},
                        status: verified && verified.ok ? 'captured' : 'pending_verification',
                        mode: 'razorpay',
                        created_at: Date.now(),
                    };
                    await persistPayment(payment);
                    if (session.onSuccess) session.onSuccess(payment);
                } catch (err) {
                    console.error('[PaymentGateway] Verify failed', err);
                    if (session.onError) session.onError(err);
                }
            },
            modal: {
                ondismiss: function () {
                    if (session.onCancel) session.onCancel();
                },
            },
        };

        try {
            const rzp = new window.Razorpay(options);
            rzp.on && rzp.on('payment.failed', function (resp) {
                if (session.onError) {
                    session.onError(new Error((resp.error && resp.error.description) || 'Payment failed'));
                }
            });
            rzp.open();
        } catch (err) {
            console.error('[PaymentGateway] Razorpay open failed', err);
            if (session.onError) session.onError(err);
        }
    }

    // ─────────────────────────────────────────────
    // PUBLIC API
    // ─────────────────────────────────────────────
    window.PaymentGateway = {
        MODE: MODE,

        open(session) {
            validateSession(session);
            lastSession = session;

            if (MODE === 'razorpay' && typeof window.Razorpay !== 'undefined') {
                renderRazorpay(session);
            } else if (MODE === 'razorpay') {
                // Try to load, and if it fails, fall back to demo
                ensureRazorpayScript()
                    .then(() => renderRazorpay(session))
                    .catch(() => renderDemoModal(session));
            } else {
                renderDemoModal(session);
            }
        },

        close() {
            closeModal();
        },

        /** Utility for pages that just want to know how much to charge. */
        computeTotal(subtotal, freeAbove = 500, deliveryFee = 40) {
            const base = Number(subtotal) || 0;
            const delivery = base >= freeAbove ? 0 : deliveryFee;
            return { subtotal: base, delivery, total: base + delivery };
        },

        /** Utility: after a successful payment, format the reference. */
        reference(payment) {
            if (!payment) return '—';
            return payment.payment_id || payment.id || '—';
        },
    };

    // ─────────────────────────────────────────────
    // URL PARAM ENTRY POINT
    // If payment-gateway.html is opened with ?amount=..., auto-open.
    // ─────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        try {
            const params = new URLSearchParams(window.location.search);
            const amt = Number(params.get('amount'));
            if (!amt || !isFinite(amt) || amt < 1) return;

            window.PaymentGateway.open({
                amount: amt,
                currency: 'INR',
                purpose: params.get('purpose') || 'Payment',
                metadata: { source: params.get('source') || 'direct' },
                onSuccess: function () {
                    const h1 = document.querySelector('.info h1');
                    const p = document.querySelector('.info p');
                    if (h1) h1.textContent = 'Payment successful ✓';
                    if (p) p.textContent = 'You can close this tab now.';
                },
                onCancel: function () {
                    const h1 = document.querySelector('.info h1');
                    if (h1) h1.textContent = 'Payment cancelled';
                },
            });
        } catch (e) {
            console.warn('[PaymentGateway] URL auto-open failed', e);
        }
    });
})();