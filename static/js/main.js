// ===== THEME TOGGLE =====
// Apply saved theme immediately to prevent flash
(function() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
})();

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeUI(newTheme);
}

function updateThemeUI(theme) {
    const icon = document.getElementById('theme-icon');
    const toggle = document.getElementById('theme-switch');

    if (icon) {
        const src = theme === 'dark' ? '/static/images/icon-moon.svg' : '/static/images/icon-sun.svg';
        icon.innerHTML = `<img class="le-icon" src="${src}" alt="">`;
    }
    if (toggle) {
        if (theme === 'dark') {
            toggle.classList.add('active');
        } else {
            toggle.classList.remove('active');
        }
    }
}

// Initialize theme UI on page load
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    updateThemeUI(savedTheme);
});

// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});

// Textarea auto-expand
document.addEventListener('DOMContentLoaded', function() {
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        });
    });
});

// @mention autocomplete for journal entries
document.addEventListener('DOMContentLoaded', function() {
    const contentTextarea = document.querySelector('#content');
    if (!contentTextarea) return; // Only run on journal entry pages
    
    // Get contacts data from the page
    const contactsList = document.querySelectorAll('.contact-quick-item');
    const contacts = Array.from(contactsList).map(item => {
        const codeEl = item.querySelector('code');
        if (codeEl) {
            const text = codeEl.textContent.trim();
            return text.replace('@', ''); // Remove @ prefix
        }
        return null;
    }).filter(c => c);
    
    // Create autocomplete dropdown
    const dropdown = document.createElement('div');
    dropdown.className = 'mention-autocomplete';
    dropdown.style.display = 'none';
    document.body.appendChild(dropdown);
    
    let currentMentionStart = -1;
    let currentQuery = '';
    let selectedIndex = -1;
    
    function showDropdown(matches, caretPos) {
        if (matches.length === 0) {
            hideDropdown();
            return;
        }
        
        // Get textarea position
        const rect = contentTextarea.getBoundingClientRect();
        
        // Position dropdown below cursor (approximate)
        dropdown.style.left = rect.left + 'px';
        dropdown.style.top = (rect.top + 30) + 'px';
        dropdown.style.display = 'block';
        
        // Populate dropdown
        dropdown.innerHTML = matches.map((contact, index) => 
            `<div class="mention-option ${index === selectedIndex ? 'selected' : ''}" data-index="${index}">
                @${contact}
            </div>`
        ).join('');
        
        // Add click handlers
        dropdown.querySelectorAll('.mention-option').forEach(option => {
            option.addEventListener('click', function() {
                insertMention(matches[parseInt(this.dataset.index)]);
            });
        });
    }
    
    function hideDropdown() {
        dropdown.style.display = 'none';
        currentMentionStart = -1;
        currentQuery = '';
        selectedIndex = -1;
    }
    
    function insertMention(contact) {
        const text = contentTextarea.value;
        const beforeMention = text.substring(0, currentMentionStart);
        const afterCursor = text.substring(contentTextarea.selectionStart);
        
        contentTextarea.value = beforeMention + '@' + contact + ' ' + afterCursor;
        
        // Move cursor after the mention
        const newPos = (beforeMention + '@' + contact + ' ').length;
        contentTextarea.setSelectionRange(newPos, newPos);
        
        hideDropdown();
        contentTextarea.focus();
    }
    
    // Handle input
    contentTextarea.addEventListener('input', function(e) {
        const text = this.value;
        const cursorPos = this.selectionStart;
        
        // Find if we're in a mention
        let mentionStart = -1;
        for (let i = cursorPos - 1; i >= 0; i--) {
            if (text[i] === '@') {
                mentionStart = i;
                break;
            }
            if (text[i] === ' ' || text[i] === '\n') {
                break;
            }
        }
        
        if (mentionStart !== -1) {
            currentMentionStart = mentionStart;
            currentQuery = text.substring(mentionStart + 1, cursorPos).toLowerCase();
            
            // Filter contacts
            const matches = contacts.filter(c => 
                c.toLowerCase().startsWith(currentQuery)
            ).slice(0, 10); // Limit to 10 results
            
            if (matches.length > 0) {
                selectedIndex = 0;
                showDropdown(matches, cursorPos);
            } else {
                hideDropdown();
            }
        } else {
            hideDropdown();
        }
    });
    
    // Handle keyboard navigation
    contentTextarea.addEventListener('keydown', function(e) {
        if (dropdown.style.display === 'none') return;
        
        const options = dropdown.querySelectorAll('.mention-option');
        const matches = Array.from(options).map(opt => opt.textContent.trim().substring(1));
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, matches.length - 1);
            showDropdown(matches, this.selectionStart);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            showDropdown(matches, this.selectionStart);
        } else if (e.key === 'Enter' && matches.length > 0) {
            e.preventDefault();
            insertMention(matches[selectedIndex]);
        } else if (e.key === 'Escape') {
            hideDropdown();
        }
    });
    
    // Hide dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (e.target !== contentTextarea && !dropdown.contains(e.target)) {
            hideDropdown();
        }
    });
});

// ===== NAV DROPDOWN =====
function toggleNavDropdown(e) {
    e.stopPropagation();
    const dropdown = e.currentTarget.closest('.nav-dropdown');
    dropdown.classList.toggle('open');
}

document.addEventListener('click', function(e) {
    const dropdown = document.querySelector('.nav-dropdown.open');
    if (dropdown && !dropdown.contains(e.target)) {
        dropdown.classList.remove('open');
    }
});

// ===== ACHIEVEMENTS EXPAND/COLLAPSE =====
function toggleAchievements() {
    const grid = document.getElementById('achievements-grid');
    const btn = document.getElementById('btn-expand-achievements');
    if (!grid || !btn) return;

    const isExpanded = grid.classList.toggle('expanded');
    btn.classList.toggle('expanded', isExpanded);
    btn.innerHTML = isExpanded
        ? 'Show Less <span class="expand-arrow">▼</span>'
        : 'Show All Achievements <span class="expand-arrow">▼</span>';
}

// ===== LEARNING ROULETTE =====
// Note: Main roulette functions are in the template for URL generation
// Wheel segment positioning is handled via CSS
