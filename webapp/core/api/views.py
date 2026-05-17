from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

from clusters.models import Node
from operations.models import Operation


# ── Dashboard helpers ─────────────────────────────────────────────────────────

_TITLE_MAP = {
    'deploy_main_manager':      'Wdrożono główny manager',
    'deploy_additional_manager':'Dodano manager',
    'deploy_worker':            'Dodano workera',
    'node_hardening':           'Utwardzono węzeł',
    'delete_node':              'Usunięto węzeł',
    'delete_cluster':           'Usunięto klaster',
    'manage_users':             'Zarządzano użytkownikami',
    'trivy_provisioning':       'Skan Trivy',
    'propagate_ansible':        'Propagacja Ansible',
    'add-node':                 'Dodano węzeł do inventory',
    'remove-node':              'Usunięto węzeł z inventory',
    'create-cluster':           'Utworzono klaster',
    'delete-cluster':           'Usunięto klaster',
}

def _op_to_activity(op):
    if op.status == Operation.Status.SUCCESS:
        ui_status, badge = 'healthy', 'HEALTHY'
    elif op.status == Operation.Status.FAILED:
        ui_status, badge = 'error', 'ERROR'
    else:
        ui_status, badge = 'deploying', 'DEPLOYING'

    playbook_key = op.playbook.replace('.yml', '')
    title = _TITLE_MAP.get(playbook_key, playbook_key.replace('_', ' ').title())

    details_parts = [f'{k}: {v}' for k, v in op.extra_vars.items() if v and k != 'node_id']
    details = ' | '.join(details_parts) if details_parts else op.playbook

    if 'delete' in playbook_key:
        icon = 'warning'
    elif 'harden' in playbook_key:
        icon = 'shield'
    elif any(w in playbook_key for w in ('deploy', 'worker', 'manager', 'add')):
        icon = 'add'
    else:
        icon = 'refresh'

    return {
        'title':     title,
        'details':   details,
        'time':      op.created_at,
        'ui_status': ui_status,
        'badge':     badge,
        'icon':      icon,
    }


def _nodes_ui_status(nodes: list) -> tuple[str | None, str | None]:
    """Derive (ui_status, label) from a list of Node objects."""
    if not nodes:
        return None, None
    statuses = {n.status for n in nodes}
    if Node.Status.DEPLOYING in statuses:
        return 'deploying', 'Deploying'
    if Node.Status.ERROR in statuses:
        return 'error', 'Error'
    return 'healthy', 'Healthy'


def _qs_ui_status(qs) -> tuple[str | None, str | None]:
    """Derive (ui_status, label) from a Node queryset — for dashboard cards."""
    if not qs.exists():
        return None, None
    if qs.filter(status=Node.Status.DEPLOYING).exists():
        return 'deploying', 'DEPLOYING'
    if qs.filter(status=Node.Status.ERROR).exists():
        return 'error', 'ERROR'
    return 'healthy', 'HEALTHY'


# ── Views ─────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        return render(request, 'login.html', {'error': 'Nieprawidłowy login lub hasło.'})
    return render(request, 'login.html')


def dashboard(request):
    all_nodes    = Node.objects.all()
    manager_qs   = Node.objects.filter(role=Node.Role.MANAGER)
    worker_qs    = Node.objects.filter(role=Node.Role.WORKER)
    recent_ops   = [_op_to_activity(op) for op in Operation.objects.order_by('-created_at')[:10]]
    return render(request, 'dashboard.html', {
        'total_nodes':    all_nodes.count(),
        'manager_count':  manager_qs.count(),
        'worker_count':   worker_qs.count(),
        'total_status':   _qs_ui_status(all_nodes),
        'manager_status': _qs_ui_status(manager_qs),
        'worker_status':  _qs_ui_status(worker_qs),
        'recent_ops':     recent_ops,
    })


def instances(request):
    from clusters.models import Cluster
    clusters_data = []
    for cluster in Cluster.objects.all():
        managers = list(cluster.nodes.filter(role='manager'))
        workers  = list(cluster.nodes.filter(role='worker'))
        ui_status, status_label = _nodes_ui_status(managers + workers)
        clusters_data.append({
            'obj':           cluster,
            'managers':      managers,
            'workers':       workers,
            'manager_count': len(managers),
            'worker_count':  len(workers),
            'ui_status':     ui_status,
            'status_label':  status_label,
        })
    return render(request, 'instances.html', {'clusters': clusters_data})


def hardening(request):
    return render(request, 'hardening.html')
