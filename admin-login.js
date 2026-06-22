(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var params = new URLSearchParams(window.location.search);
        var message = document.getElementById('loginMessage');
        var username = document.getElementById('username');

        if (params.get('expired')) {
            message.className = 'success-banner';
            message.textContent = 'Your session expired. Sign in again.';
            message.hidden = false;
        } else if (params.get('error')) {
            message.textContent = 'Invalid username or password.';
            message.hidden = false;
        } else if (params.get('logged_out')) {
            message.className = 'success-banner';
            message.textContent = 'You have been signed out.';
            message.hidden = false;
        }

        if (username) {
            username.focus();
        }
    });
})();
