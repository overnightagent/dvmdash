function showLoadingSpinner() {
    const loadingDiv = document.getElementById('loading-spinner');
    if (loadingDiv) {
        // Reset any error messages
        const errorText = loadingDiv.querySelector('.loading-text.error');
        if (errorText) {
            errorText.style.display = 'none';
        }
        // Show the loading spinner
        loadingDiv.style.display = 'flex';
        loadingDiv.querySelector('.spinner-border').style.display = 'block';
        loadingDiv.querySelector('.loading-text:not(.error)').style.display = 'block';
    }
}

function hideLoadingSpinner() {
    const loadingDiv = document.getElementById('loading-spinner');
    if (loadingDiv) {
        loadingDiv.style.display = 'none';
    }
}

function showError(message) {
    const loadingDiv = document.getElementById('loading-spinner');
    if (loadingDiv) {
        // Hide the spinner but keep the div visible
        loadingDiv.style.display = 'flex';
        loadingDiv.querySelector('.spinner-border').style.display = 'none';
        loadingDiv.querySelector('.loading-text:not(.error)').style.display = 'none';
        
        // Show error message
        let errorText = loadingDiv.querySelector('.loading-text.error');
        if (!errorText) {
            errorText = document.createElement('div');
            errorText.className = 'loading-text error';
            loadingDiv.querySelector('.d-flex').appendChild(errorText);
        }
        errorText.textContent = message;
        errorText.style.display = 'block';
        
        // Hide error after 5 seconds
        setTimeout(() => {
            hideLoadingSpinner();
        }, 5000);
    }
}

// Update the redirectToDVM function to show loading state
function redirectToDVM() {
    var selectedValue = document.getElementById('dvm-select').value;
    if (selectedValue) {
        showLoadingSpinner();
        
        // Add error handling for navigation timeout
        const timeoutId = setTimeout(() => {
            showError('Loading is taking longer than expected. Please try again.');
        }, 10000); // Show error after 10 seconds
        
        try {
            window.location.href = '/dvm/' + selectedValue;
        } catch (error) {
            showError('An error occurred while loading the DVM data.');
            clearTimeout(timeoutId);
        }
        return false;
    }
    return false;
}