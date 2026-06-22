(function () {
    'use strict';

    const CONFIG = [
        {
            key: 'contact_messages',
            title: 'Contact messages',
            description: 'Feedback and questions sent through the contact form.',
            columns: [
                { label: 'Created', render: (row) => formatDate(row.created_at) },
                { label: 'Name', field: 'name' },
                { label: 'Email', field: 'email' },
                { label: 'Phone', field: 'phone' },
                { label: 'Subject', field: 'subject' },
                { label: 'Message', field: 'message', long: true }
            ]
        },
        {
            key: 'donations',
            title: 'Donation submissions',
            description: 'Food donation entries and pickup details.',
            columns: [
                { label: 'Created', render: (row) => formatDate(row.created_at) },
                { label: 'Donor', field: 'name' },
                { label: 'Email', field: 'email' },
                { label: 'Phone', field: 'phone' },
                { label: 'Food', render: (row) => `${row.food_type || 'N/A'} / ${row.quantity || 'N/A'}` },
                { label: 'Pickup', render: (row) => `${row.pickup_time || 'N/A'} / ${row.pickup_method || 'N/A'}` },
                { label: 'Recurring', render: (row) => renderBadge(row.recurring ? 'Yes' : 'No') },
                { label: 'Description', field: 'description', long: true },
                { label: 'Files', render: renderAttachments }
            ]
        },
        {
            key: 'requests',
            title: 'Recipient registrations',
            description: 'Requests from organizations looking for food support.',
            columns: [
                { label: 'Created', render: (row) => formatDate(row.created_at) },
                { label: 'Organization', field: 'org_name' },
                { label: 'Type', field: 'org_type' },
                { label: 'Registration #', field: 'reg_number' },
                { label: 'Contact', render: (row) => `${row.contact_name || 'N/A'} / ${row.contact_email || 'N/A'}` },
                { label: 'Phone', field: 'contact_phone' },
                { label: 'Beneficiaries', field: 'beneficiaries' },
                { label: 'Needs', field: 'food_needs' },
                { label: 'Address', field: 'pickup_address', long: true },
                { label: 'Description', field: 'description', long: true },
                { label: 'Files', render: renderAttachments }
            ]
        },
        {
            key: 'volunteers',
            title: 'Volunteer signups',
            description: 'People offering time and support.',
            columns: [
                { label: 'Created', render: (row) => formatDate(row.created_at) },
                { label: 'Name', field: 'name' },
                { label: 'Email', field: 'email' },
                { label: 'Phone', field: 'phone' },
                { label: 'Area', field: 'area' },
                { label: 'Role', field: 'role' },
                { label: 'Availability', field: 'availability' },
                { label: 'Bio', field: 'bio', long: true }
            ]
        },
        {
            key: 'partnerships',
            title: 'Partnership inquiries',
            description: 'Business, logistics, and institutional partnership requests.',
            columns: [
                { label: 'Created', render: (row) => formatDate(row.created_at) },
                { label: 'Organization', field: 'organization_name' },
                { label: 'Type', field: 'organization_type' },
                { label: 'Contact', field: 'contact_person' },
                { label: 'Email', field: 'email' },
                { label: 'Phone', field: 'phone' },
                { label: 'Location', field: 'location' },
                { label: 'Interest', field: 'interest', long: true }
            ]
        },
        {
            key: 'quick_requests',
            title: 'Quick donation requests',
            description: 'One-click requests raised from the available donation cards.',
            columns: [
                { label: 'Created', render: (row) => formatDate(row.created_at) },
                { label: 'Title', field: 'title' },
                { label: 'Donor', field: 'donor' },
                { label: 'Location', field: 'location' },
                { label: 'Food type', field: 'food_type' },
                { label: 'Available until', field: 'available_date' },
                { label: 'Summary', field: 'summary', long: true }
            ]
        }
    ];

    const state = {
        data: null,
        query: ''
    };

    function formatDate(value) {
        if (!value) {
            return 'N/A';
        }

        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }

        return new Intl.DateTimeFormat([], {
            dateStyle: 'medium',
            timeStyle: 'short'
        }).format(date);
    }

    function renderBadge(label) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = label;
        return badge;
    }

    function renderAttachments(row) {
        const attachments = Array.isArray(row.attachments) ? row.attachments : [];
        if (!attachments.length) {
            return document.createTextNode('N/A');
        }

        const wrap = document.createElement('div');
        wrap.className = 'file-list';

        attachments.forEach((attachment) => {
            const link = document.createElement('a');
            link.className = 'file-link';
            link.href = attachment.url;
            link.target = '_blank';
            link.rel = 'noreferrer';
            link.textContent = `${attachment.label}: ${attachment.name}`;
            wrap.appendChild(link);
        });

        return wrap;
    }

    function cellValue(record, column) {
        if (typeof column.render === 'function') {
            return column.render(record);
        }

        const value = record[column.field];
        if (value === null || value === undefined || value === '') {
            return 'N/A';
        }

        if (typeof value === 'boolean') {
            return value ? 'Yes' : 'No';
        }

        return String(value);
    }

    function buildSummaryCards(summary) {
        const grid = document.getElementById('summaryGrid');
        grid.innerHTML = '';

        const cards = [
            ['Total submissions', summary.total, 'total'],
            ['Contact messages', summary.contact_messages, ''],
            ['Donation submissions', summary.donations, ''],
            ['Recipient registrations', summary.requests, ''],
            ['Volunteer signups', summary.volunteers, 'volunteers'],
            ['Partnership inquiries', summary.partnerships, 'partnerships'],
            ['Quick requests', summary.quick_requests, '']
        ];

        cards.forEach(([label, value, extraClass]) => {
            const card = document.createElement('div');
            card.className = `summary-card${extraClass ? ` ${extraClass}` : ''}`;

            const title = document.createElement('div');
            title.className = 'summary-label';
            title.textContent = label;

            const count = document.createElement('div');
            count.className = 'summary-value';
            count.textContent = String(value ?? 0);

            card.appendChild(title);
            card.appendChild(count);
            grid.appendChild(card);
        });
    }

    function renderTable(section, records) {
        const wrap = document.createElement('div');
        wrap.className = 'dataset';

        const head = document.createElement('div');
        head.className = 'dataset-head';

        const title = document.createElement('h3');
        title.textContent = section.title;

        const desc = document.createElement('p');
        desc.textContent = `${records.length} record${records.length === 1 ? '' : 's'}`;

        head.appendChild(title);
        head.appendChild(desc);
        wrap.appendChild(head);

        if (!records.length) {
            const empty = document.createElement('div');
            empty.className = 'empty';
            empty.textContent = 'No entries yet.';
            wrap.appendChild(empty);
            return wrap;
        }

        const tableWrap = document.createElement('div');
        tableWrap.className = 'table-wrap';

        const table = document.createElement('table');
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');

        section.columns.forEach((column) => {
            const th = document.createElement('th');
            th.textContent = column.label;
            headerRow.appendChild(th);
        });

        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        records.forEach((record) => {
            const row = document.createElement('tr');
            row.dataset.search = JSON.stringify(record).toLowerCase();

            section.columns.forEach((column) => {
                const td = document.createElement('td');
                if (column.long) {
                    td.className = 'long';
                }

                const value = cellValue(record, column);
                if (value instanceof Node) {
                    td.appendChild(value);
                } else {
                    td.textContent = value;
                }

                row.appendChild(td);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        tableWrap.appendChild(table);
        wrap.appendChild(tableWrap);
        return wrap;
    }

    function renderSections(data) {
        const container = document.getElementById('tables');
        container.innerHTML = '';

        CONFIG.forEach((section) => {
            const records = Array.isArray(data.sections?.[section.key]) ? data.sections[section.key] : [];
            container.appendChild(renderTable(section, records));
        });
    }

    function applySearchFilter() {
        const query = state.query.trim().toLowerCase();
        const rows = document.querySelectorAll('#tables tbody tr');

        rows.forEach((row) => {
            const haystack = row.dataset.search || '';
            row.style.display = !query || haystack.includes(query) ? '' : 'none';
        });
    }

    function setStatus(text) {
        document.getElementById('statusText').textContent = text;
    }

    async function loadDashboard() {
        const summaryGrid = document.getElementById('summaryGrid');
        const tables = document.getElementById('tables');

        setStatus('Loading...');
        summaryGrid.innerHTML = '';
        tables.innerHTML = '<div class="loading">Loading records...</div>';

        try {
            const response = await fetch('/api/admin/data', {
                headers: {
                    Accept: 'application/json'
                }
            });

            if (response.status === 401) {
                window.location.href = '/admin-login?expired=1';
                return;
            }

            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Failed to load dashboard data.');
            }

            state.data = payload;
            buildSummaryCards(payload.summary || {});
            renderSections(payload);
            applySearchFilter();
            setStatus(`Last refreshed ${formatDate(payload.generated_at)}`);
        } catch (error) {
            tables.innerHTML = `<div class="error">${error.message || 'Unable to load dashboard.'}</div>`;
            setStatus('Load failed');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const searchInput = document.getElementById('searchInput');
        const refreshBtn = document.getElementById('refreshBtn');

        searchInput.addEventListener('input', (event) => {
            state.query = event.target.value || '';
            applySearchFilter();
        });

        refreshBtn.addEventListener('click', loadDashboard);

        loadDashboard();
    });
})();
