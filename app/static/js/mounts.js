// ES5 호환 스크립트로 마운트 관리 UI를 제어합니다.
(function () {
    var mountListEl = document.getElementById('mount-list');
    var mountForm = document.getElementById('mount-form');
    var mountMessage = document.getElementById('mount-message');
    var mountCounter = document.getElementById('mount-counter');
    var mountFormTitle = document.getElementById('mount-form-title');
    var mountIdInput = document.getElementById('mount-id');
    var mountNameInput = document.getElementById('mount-name');
    var mountHostPathInput = document.getElementById('mount-host-path');
    var mountOrderInput = document.getElementById('mount-display-order');
    var mountEnabledInput = document.getElementById('mount-enabled');
    var mountResetButton = document.getElementById('mount-reset-button');
    var mountSaveButton = document.getElementById('mount-save-button');
    var driveSelect = document.getElementById('drive-select');
    var applyDriveButton = document.getElementById('apply-drive-button');
    var maxMounts = 5;
    var editingId = null;

    if (!mountListEl || !mountForm) {
        return;
    }

    var maxAttr = mountListEl.getAttribute('data-max');
    if (maxAttr) {
        maxMounts = parseInt(maxAttr, 10) || maxMounts;
    }

    function setMessage(text, level) {
        if (!mountMessage) {
            return;
        }
        var colors = {
            success: 'bg-green-100 text-green-800',
            error: 'bg-red-100 text-red-800',
            info: 'bg-blue-100 text-blue-800'
        };
        var colorClass = colors[level] || colors.info;
        mountMessage.className = 'mt-4 p-3 rounded text-sm ' + colorClass;
        mountMessage.textContent = text;
        mountMessage.classList.remove('hidden');
    }

    function clearMessage() {
        if (!mountMessage) {
            return;
        }
        mountMessage.className = 'mt-4 hidden';
        mountMessage.textContent = '';
    }

    function request(method, url, payload, callback) {
        var xhr = new XMLHttpRequest();
        xhr.open(method, url, true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== 4) {
                return;
            }
            var response = null;
            if (xhr.responseText) {
                try {
                    response = JSON.parse(xhr.responseText);
                } catch (err) {
                    response = null;
                }
            }
            if (xhr.status >= 200 && xhr.status < 300) {
                callback(null, response || {});
            } else {
                var message = '요청 처리 중 오류가 발생했습니다.';
                if (response && response.error) {
                    message = response.error;
                }
                callback(message);
            }
        };
        xhr.send(payload ? JSON.stringify(payload) : null);
    }

    function updateCounter(current, maximum) {
        if (!mountCounter) {
            return;
        }
        var text = current + ' / ' + maximum;
        if (current >= maximum) {
            text += ' (최대)';
        }
        mountCounter.textContent = text;
    }

    function renderMounts(mounts) {
        mountListEl.innerHTML = '';
        if (!mounts.length) {
            var empty = document.createElement('p');
            empty.className = 'text-sm text-gray-500';
            empty.textContent = '등록된 드라이브가 없습니다.';
            mountListEl.appendChild(empty);
            return;
        }

        for (var i = 0; i < mounts.length; i++) {
            var mount = mounts[i];
            var row = document.createElement('div');
            row.className = 'border rounded px-3 py-2 flex flex-col md:flex-row md:items-center justify-between gap-2 mb-2';

            var info = document.createElement('div');
            var nameEl = document.createElement('p');
            nameEl.className = 'font-medium';
            nameEl.textContent = mount.name + ' (' + mount.container_path + ')';

            var meta = document.createElement('p');
            meta.className = 'text-sm text-gray-600';
            meta.textContent = '호스트: ' + mount.host_path + ' · ' + (mount.is_enabled ? '활성화' : '비활성화');

            info.appendChild(nameEl);
            info.appendChild(meta);

            var actions = document.createElement('div');
            actions.className = 'flex gap-2';

            var editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'text-sm text-blue-600 hover:underline';
            editBtn.textContent = '수정';
            editBtn.addEventListener('click', createEditHandler(mount));

            var deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'text-sm text-red-600 hover:underline';
            deleteBtn.textContent = '삭제';
            deleteBtn.addEventListener('click', createDeleteHandler(mount.id));

            actions.appendChild(editBtn);
            actions.appendChild(deleteBtn);

            row.appendChild(info);
            row.appendChild(actions);
            mountListEl.appendChild(row);
        }
    }

    function createEditHandler(mount) {
        return function () {
            editingId = mount.id;
            mountIdInput.value = mount.id;
            mountNameInput.value = mount.name;
            mountHostPathInput.value = mount.host_path;
            mountOrderInput.value = mount.display_order;
            mountEnabledInput.checked = mount.is_enabled ? true : false;
            mountFormTitle.textContent = '마운트 수정: ' + mount.name;
            clearMessage();
            mountSaveButton.disabled = false;
        };
    }

    function createDeleteHandler(mountId) {
        return function () {
            if (!window.confirm('정말로 이 마운트를 삭제하시겠습니까?')) {
                return;
            }
            request('DELETE', '/api/mounts/' + mountId, null, function (err) {
                if (err) {
                    setMessage(err, 'error');
                    return;
                }
                setMessage('삭제되었습니다.', 'success');
                if (editingId === mountId) {
                    resetForm();
                }
                loadMounts();
            });
        };
    }

    function resetForm() {
        editingId = null;
        mountIdInput.value = '';
        mountNameInput.value = '';
        mountHostPathInput.value = '';
        mountOrderInput.value = '0';
        mountEnabledInput.checked = true;
        mountFormTitle.textContent = '새 마운트 추가';
        clearMessage();
    }

    function updateFormAvailability(currentCount, maximum) {
        if (!mountSaveButton) {
            return;
        }
        var isFull = !editingId && currentCount >= maximum;
        mountSaveButton.disabled = isFull;
        mountSaveButton.title = isFull ? '최대 개수에 도달했습니다. 기존 항목을 수정하거나 삭제하세요.' : '';
    }

    function handleFormSubmit(event) {
        event.preventDefault();
        var payload = {
            name: mountNameInput.value,
            host_path: mountHostPathInput.value,
            display_order: mountOrderInput.value ? parseInt(mountOrderInput.value, 10) : 0,
            is_enabled: mountEnabledInput.checked
        };

        var method = 'POST';
        var url = '/api/mounts';
        if (editingId) {
            method = 'PUT';
            url = '/api/mounts/' + editingId;
        }

        request(method, url, payload, function (err) {
            if (err) {
                setMessage(err, 'error');
                return;
            }
            setMessage('저장되었습니다.', 'success');
            resetForm();
            loadMounts();
        });
    }

    function loadMounts() {
        request('GET', '/api/mounts', null, function (err, data) {
            if (err) {
                setMessage(err, 'error');
                return;
            }
            var mounts = data.mounts || [];
            renderMounts(mounts);
            updateCounter(data.current_count || mounts.length, data.max_mounts || maxMounts);
            updateFormAvailability(data.current_count || mounts.length, data.max_mounts || maxMounts);
        });
    }

    function loadDrives() {
        request('GET', '/api/drives', null, function (err, data) {
            if (err) {
                return;
            }
            var drives = data.drives || [];
            renderDriveOptions(drives);
        });
    }

    function renderDriveOptions(drives) {
        if (!driveSelect) {
            return;
        }
        driveSelect.innerHTML = '';
        var placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = drives.length ? '드라이브를 선택하세요' : '드라이브 정보를 가져올 수 없습니다';
        driveSelect.appendChild(placeholder);
        for (var i = 0; i < drives.length; i++) {
            var option = document.createElement('option');
            option.value = drives[i].path;
            option.textContent = drives[i].letter + ': (' + (drives[i].label || drives[i].path) + ')';
            driveSelect.appendChild(option);
        }
    }

    function applySelectedDrive() {
        if (!driveSelect) {
            return;
        }
        var value = driveSelect.value;
        if (value) {
            mountHostPathInput.value = value;
        }
    }

    mountForm.addEventListener('submit', handleFormSubmit);
    if (mountResetButton) {
        mountResetButton.addEventListener('click', resetForm);
    }
    if (applyDriveButton) {
        applyDriveButton.addEventListener('click', applySelectedDrive);
    }
    loadMounts();
    loadDrives();
})();
