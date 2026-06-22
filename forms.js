(function () {
    'use strict';

    async function postForm(endpoint, formData) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        });

        let payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            payload = {};
        }

        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'Submission failed. Please try again.');
        }

        return payload;
    }

    async function postJson(endpoint, data) {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data)
        });

        let payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            payload = {};
        }

        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'Submission failed. Please try again.');
        }

        return payload;
    }

    function normalize(value) {
        return (value || '').toString().trim().toLowerCase();
    }

    function toggleRecurringOptions() {
        const recurring = document.getElementById('recurring');
        const recurringOptions = document.getElementById('recurringOptions');

        if (!recurring || !recurringOptions) {
            return;
        }

        recurringOptions.style.display = recurring.checked ? 'block' : 'none';
    }

    function bindForm(formId, endpoint, afterSuccess) {
        const form = document.getElementById(formId);

        if (!form) {
            return;
        }

        form.addEventListener('submit', async function (event) {
            event.preventDefault();

            const button = form.querySelector('button[type="submit"]');
            const originalLabel = button ? button.textContent : '';

            if (button) {
                button.disabled = true;
                button.textContent = 'Submitting...';
            }

            try {
                const payload = await postForm(endpoint, new FormData(form));
                alert(payload.message || 'Submitted successfully.');
                form.reset();

                if (typeof afterSuccess === 'function') {
                    afterSuccess();
                }
            } catch (error) {
                alert(error.message || 'Submission failed. Please try again.');
            } finally {
                if (button) {
                    button.disabled = false;
                    button.textContent = originalLabel;
                }
            }
        });
    }

    function setupFaqAccordion() {
        const faqQuestions = document.querySelectorAll('.faq-question');

        if (!faqQuestions.length) {
            return;
        }

        faqQuestions.forEach(function (question) {
            question.addEventListener('click', function () {
                const answer = this.nextElementSibling;
                const isActive = this.classList.contains('active');

                document.querySelectorAll('.faq-answer').forEach(function (item) {
                    item.classList.remove('show');
                });
                document.querySelectorAll('.faq-question').forEach(function (item) {
                    item.classList.remove('active');
                });

                if (!isActive && answer) {
                    this.classList.add('active');
                    answer.classList.add('show');
                }
            });
        });
    }

    function setupDonationFilters() {
        const filterType = document.getElementById('filterType');
        const filterLocation = document.getElementById('filterLocation');
        const filterDate = document.getElementById('filterDate');
        const cards = Array.prototype.slice.call(document.querySelectorAll('.donation-item'));

        if (!cards.length || (!filterType && !filterLocation && !filterDate)) {
            return;
        }

        function applyFilters() {
            const typeValue = normalize(filterType ? filterType.value : '');
            const locationValue = normalize(filterLocation ? filterLocation.value : '');
            const dateValue = filterDate ? filterDate.value : '';

            cards.forEach(function (card) {
                const cardType = normalize(card.dataset.foodType);
                const cardLocation = normalize(card.dataset.location);
                const cardDate = card.dataset.availableDate || '';

                const matchesType = !typeValue || cardType === typeValue;
                const matchesLocation = !locationValue || cardLocation.indexOf(locationValue) !== -1;
                const matchesDate = !dateValue || cardDate === dateValue;

                card.style.display = matchesType && matchesLocation && matchesDate ? '' : 'none';
            });
        }

        if (filterType) {
            filterType.addEventListener('change', applyFilters);
        }
        if (filterLocation) {
            filterLocation.addEventListener('input', applyFilters);
        }
        if (filterDate) {
            filterDate.addEventListener('change', applyFilters);
        }

        applyFilters();
    }

    function setupQuickRequests() {
        const buttons = document.querySelectorAll('.request-donation-btn');

        if (!buttons.length) {
            return;
        }

        buttons.forEach(function (button) {
            button.addEventListener('click', async function () {
                const card = button.closest('.donation-item');

                if (!card) {
                    return;
                }

                const titleEl = card.querySelector('.donation-header h4');
                const donorEl = card.querySelector('.donor-badge');
                const detailsEl = card.querySelector('.donation-details');
                const originalLabel = button.textContent;

                button.disabled = true;
                button.textContent = 'Sending...';

                try {
                    const payload = await postJson('/api/quick-requests', {
                        title: titleEl ? titleEl.textContent.trim() : '',
                        donor: donorEl ? donorEl.textContent.trim() : '',
                        location: card.dataset.location || '',
                        food_type: card.dataset.foodType || '',
                        available_date: card.dataset.availableDate || '',
                        summary: detailsEl ? detailsEl.textContent.trim() : ''
                    });

                    alert(payload.message || 'Request recorded successfully.');
                } catch (error) {
                    alert(error.message || 'Unable to submit request.');
                } finally {
                    button.disabled = false;
                    button.textContent = originalLabel;
                }
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindForm('contactForm', '/api/contact');
        bindForm('donationForm', '/api/donations', toggleRecurringOptions);
        bindForm('recipientForm', '/api/requests');
        bindForm('volunteerForm', '/api/volunteers');
        bindForm('partnerForm', '/api/partnerships');

        const recurring = document.getElementById('recurring');
        if (recurring) {
            recurring.addEventListener('change', toggleRecurringOptions);
        }
        toggleRecurringOptions();

        setupFaqAccordion();
        setupDonationFilters();
        setupQuickRequests();
    });
})();
