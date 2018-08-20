# TODO: 1) дописать документацию
# TODO: 2) Рефакторинг
# TODO: 3) Логирование
# TODO: 4) еще можно выделить в сущность даже функции парсера!
import sys
import os
import uuid
from app.command_parser import get_parsers
from app.formatted_argparse import FormattedParser
from app.help_functions import *
from app.parser_args import ParserArgs
from app.printer import Printer
from app.user_wrapper import (
    UserWrapper,
    UserWrapperStorage,
    UserWrapperController,
    LoginError,
    LogoutError,
    SaveUserError
)

try:
    from lib.calistra_lib.storage.json_serializer import JsonDatabase
    from lib.calistra_lib.user.user import User
    from lib.calistra_lib.task.task import Task, TaskStatus
    from lib.calistra_lib.queue.queue import Queue
    from lib.calistra_lib.exceptions.base_exception import AppError
    from lib.calistra_lib.interface import Interface

except ImportError:
    from calistra_lib.storage.json_serializer import JsonDatabase
    from calistra_lib.user.user import User
    from calistra_lib.task.task import Task, TaskStatus
    from calistra_lib.queue.queue import Queue
    from calistra_lib.exceptions.base_exception import AppError
    from calistra_lib.interface import Interface

FOLDER = os.path.join(os.environ['HOME'], 'calistra_data')
TASKS_FILE = os.path.join(FOLDER, 'tasks.json')
QUEUES_FILE = os.path.join(FOLDER, 'queues.json')
USERS_FILE = os.path.join(FOLDER, 'users.json')
AUTH_FILE = os.path.join(FOLDER, 'auth.json')
ONLINE = os.path.join(FOLDER, 'online_user.json')
FILES = [
    (TASKS_FILE, '[]'),
    (QUEUES_FILE, '[]'),
    (USERS_FILE, '[]'),
    (AUTH_FILE, '[]'),
    (ONLINE, '""')
]

ERROR_CODE = 1
TASK_KEY_BYTES = 8
QUEUE_KEY_BYTES = 4


def apply_settings():
    pass


def check_program_data_files(folder, files):
    if not os.path.exists(folder):
        os.mkdir(folder)
    for file in files:
        if not os.path.exists(file[0]):
            with open(file[0], 'w') as file_obj:
                file_obj.write(file[1])


def run() -> int:
    """
    Start program
    :return: int - exit code
    """
    # TODO: сделать функцию применения настроек
    # program settings
    apply_settings()
    check_program_data_files(FOLDER, FILES)

    parser = get_parsers()
    args = vars(parser.parse_args())

    # check that target is defined
    target = args.pop(ParserArgs.TARGET.name)
    if target is None:
        parser.error('target is required')

    # check that action is defined
    action = args.pop(ParserArgs.ACTION)
    if action is None:
        FormattedParser.active_sub_parser.error('action is required')

    users_wrapper_storage = UserWrapperStorage(
        JsonDatabase(AUTH_FILE, [UserWrapper]),
        JsonDatabase(ONLINE, [])
    )

    library = Interface(
        users_wrapper_storage.online_user,
        JsonDatabase(QUEUES_FILE, [Queue]),
        JsonDatabase(USERS_FILE, [User]),
        JsonDatabase(TASKS_FILE, [Task])
    )

    # update reminders deadlines queue and other
    library.update_all()
    _show_new_messages(library)

    # check that target is user and do action with it
    if target == ParserArgs.USER.name:
        if action == ParserArgs.ADD:
            return _add_user(
                nick=args.pop(ParserArgs.NICKNAME.name),
                password=args.pop(ParserArgs.PASSWORD.name),
                users_storage=users_wrapper_storage,
                library=library
            )

        if action == ParserArgs.LOGIN.name:
            return _login(
                nick=args.pop(ParserArgs.NICKNAME.name),
                password=args.pop(ParserArgs.PASSWORD.name),
                users_storage=users_wrapper_storage,
                library=library
            )

        if action == ParserArgs.LOGOUT.name:
            return _logout(users_wrapper_storage)

        if action == ParserArgs.SHOW:
            long = args.pop(ParserArgs.LONG.dest)
            sortby = args.pop(ParserArgs.SORT_BY.dest)
            return _show_user_tasks(library, long, sortby)

    # check that target is queue and do action with it
    if target == ParserArgs.QUEUE.name:
        if action == ParserArgs.ADD:
            return _add_queue(
                name=args.pop(ParserArgs.QUEUE_NAME.name).strip(' '),
                library=library
            )

        if action == ParserArgs.DELETE:
            return _del_queue(
                key=args.pop(ParserArgs.QUEUE_NAME.name).strip(' '),
                recursive=args.pop(ParserArgs.RECURSIVE.dest),
                library=library
            )

        if action == ParserArgs.SET:
            key = args.pop(ParserArgs.KEY.name)
            new_name = args.pop(ParserArgs.NEW_NAME.dest)
            if new_name is None:
                parser.active_sub_parser.help()
                return 0

            return _edit_queue(
                key=key,
                new_name=new_name,
                library=library
            )

        if action == ParserArgs.SHOW:
            return _show_queue_tasks(
                key=args.pop(ParserArgs.KEY.name),
                opened=args.pop(ParserArgs.OPEN_TASKS.dest),
                archive=args.pop(ParserArgs.SOLVED_TASKS.dest),
                failed=args.pop(ParserArgs.FAILED_TASKS.dest),
                long=args.pop(ParserArgs.LONG.dest),
                library=library,
                sortby=args.pop(ParserArgs.SORT_BY.dest)
            )

        if action == ParserArgs.FIND:
            name = args.pop(ParserArgs.QUEUE_NAME.name)
            return _find_queues(name, library)

    # check that target is task and do action with it
    if target == ParserArgs.TASK.name:
        if action == ParserArgs.ADD:
            return _add_task(args, library)

        if action == ParserArgs.SET:
            return _edit_task(args, library)

        if action == ParserArgs.DELETE:
            return _del_task(args, library)

        if action == ParserArgs.SHOW:
            return _show_task(
                args.pop(ParserArgs.KEY.name),
                library,
                args.pop(ParserArgs.LONG.dest)
            )

        if action == ParserArgs.FIND:
            return _find_task(args.pop(ParserArgs.TASK_NAME.name), library)

        if action == ParserArgs.ACTIVATE:
            key = args.pop(ParserArgs.KEY.name)
            return _activate_task(key, library)

    # check that target is plan and do action with it
    if target == ParserArgs.PLAN.name:
        if action == ParserArgs.ADD:
            pass

    if target == ParserArgs.NOTIFICATIONS.name:
        if action == ParserArgs.SHOW:
            notifications = library.online_user.notifications
            print(
                'Notifications for user "{}":'.format(library.online_user.nick))
            if _show_messages(notifications):
                print('Notifications not found!')

        if action == ParserArgs.DELETE:
            _del_notifications(
                library,
                _all=args.pop(ParserArgs.ALL.dest),
                old=args.pop(ParserArgs.OLD.dest)
            )


# =================================================
# functions for work with user's account instance =
# =================================================
def _add_user(nick, password, users_storage, library: Interface):
    try:
        users_storage.add_user(nick, password)
    except SaveUserError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    uid = uuid.uuid4().int
    queue_key = os.urandom(QUEUE_KEY_BYTES).hex()
    library.add_user(nick, uid, queue_key)
    print('User "{}" successfully created!'.format(nick))
    return 0


def _login(nick, password, users_storage, library) -> int:
    controller = UserWrapperController(users_storage)
    try:
        controller.login(nick, password)
    except LoginError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('User "{}" now is online.'.format(nick))
    library.set_online_user(nick)
    _show_new_messages(library)
    return 0


def _logout(users_storage) -> int:
    controller = UserWrapperController(users_storage)
    try:
        controller.logout()
    except LogoutError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('All users now offline.')
    return 0


def _show_new_messages(library) -> int:
    if library.online_user is None:
        return ERROR_CODE
    new_messages = library.online_user.new_messages
    if new_messages:
        print('New messages:')
        _show_messages(new_messages)
        library.clear_new_messages()
        print(Printer.SEPARATOR)
    return 0


def _show_messages(messages) -> int:
    if messages:
        reminders = []
        for message in messages:  # type: str
            if message.lower().startswith('reminder'):
                reminders.append(message)
                messages.remove(message)

        Printer.print_reminders(reversed(reminders))
        Printer.print_notifications(reversed(messages))
        return 0

    return ERROR_CODE


def _del_notifications(library, _all, old) -> int:
    try:
        library.clear_notifications(old)

    except ValueError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Notifications deleted')
    return 0


def _show_user_tasks(library, long, sortby) -> int:
    try:
        print('User: "{}".'.format(library.get_online_user().nick))
        queues = library.get_user_queues()
        Printer.print_queues(queues)

    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    if sortby is None:
        sortby = ParserArgs.TASK_PRIORITY.dest.lower()

    author_tasks, responsible_tasks = library.get_user_tasks()
    print('Tasks:')
    author_tasks.sort(key=lambda x: x.__dict__[sortby], reverse=True)
    responsible_tasks.sort(key=lambda x: x.__dict__[sortby], reverse=True)
    Printer.print_tasks(author_tasks, "Author", long)
    Printer.print_tasks(responsible_tasks, "Responsible", long)
    return 0


# =================================================
# functions for work with queue instance          =
# =================================================
def _add_queue(name, library):
    key = os.urandom(QUEUE_KEY_BYTES).hex()
    try:
        added_queue = library.add_queue(name=name, key=key)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Queue "{}" added. It\'s key - {}'.format(added_queue.name, key))
    return 0


def _del_queue(key, recursive, library):
    try:
        deleted_queue = library.remove_queue(
            key=key,
            recursive=recursive)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Queue "{}" deleted'.format(deleted_queue.name))
    return 0


def _edit_queue(key, new_name, library):
    try:
        new_name = check_str_len(new_name)
    except ValueError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    try:
        library.edit_queue(key, new_name)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Queue {} now have new name "{}"'.format(key, new_name))
    return 0


def _show_queue(library) -> int:
    # TODO: сделать чтобы показывались все таски
    try:
        queues = library.get_user_queues()
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    for queue in queues:
        print('Queue name: "{}", key = {}'.format(queue.name, queue.key))
    return 0


def _show_queue_tasks(key, library, opened, archive, failed, long, sortby):

    def load_tasks(task_keys):
        _tasks = []
        for _key in task_keys:
            task = library.get_task(key=_key)
            _tasks.append(task)
        _tasks.sort(key=lambda x: x.__dict__[sortby], reverse=True)
        return _tasks

    if not opened and not archive and not failed:
        opened = True
    try:
        queue = library.get_queue(key)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    if sortby is None:
        sortby = ParserArgs.TASK_PRIORITY.dest.lower()

    print('Queue: "{}", key {}\nTasks:'.format(queue.name, queue.key))

    if opened:
        tasks = load_tasks(queue.opened_tasks)
        Printer.print_tasks(tasks, TaskStatus.OPENED, long, Printer.CL_YELLOW)

    if archive:
        tasks = load_tasks(queue.solved_tasks)
        Printer.print_tasks(tasks, TaskStatus.SOLVED, long, Printer.CL_BLUE)

    if failed:
        tasks = load_tasks(queue.failed_tasks)
        Printer.print_tasks(tasks, TaskStatus.FAILED, long, Printer.CL_RED)

    return 0


def _find_queues(name, library: Interface) -> int:
    queues = library.find_queues(name)
    print('Search:')
    Printer.print_queues(queues, 'Results for "{}"'.format(name))
    return 0


# =================================================
# functions for work with task instance           =
# =================================================
def _add_task(args, library) -> int:
    key = os.urandom(TASK_KEY_BYTES).hex()
    queue_key = args.pop(ParserArgs.TASK_QUEUE.dest)

    try:
        name = args.pop(ParserArgs.TASK_NAME.name).strip(' ')
        name = check_str_len(name)

        description = args.pop(ParserArgs.TASK_DESCRIPTION.dest)
        description = check_str_len(description)

        linked = args.pop(ParserArgs.TASK_LINKED.dest)
        linked = check_link_correctness(linked)

        responsible = args.pop(ParserArgs.TASK_RESPONSIBLE.dest)
        responsible = check_responsible_correctness(responsible)

        priority = args.pop(ParserArgs.TASK_PRIORITY.dest)
        priority = check_priority_correctness(priority)

        progress = args.pop(ParserArgs.TASK_PROGRESS.dest)
        progress = check_progress_correctness(progress)

        start = args.pop(ParserArgs.TASK_START.dest)
        start = check_time_format(start)

        deadline = args.pop(ParserArgs.TASK_DEADLINE.dest)
        deadline = check_time_format(deadline)

        tags = args.pop(ParserArgs.TASK_TAGS.dest)
        tags = check_tags_correctness(tags)

        reminder = args.pop(ParserArgs.TASK_REMINDER.dest)
        reminder = check_reminder_format(reminder)

    except ValueError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    try:
        library.add_task(
            name=name,
            queue_key=queue_key,
            description=description,
            parent=args.pop(ParserArgs.TASK_PARENT.dest),
            linked=linked,
            responsible=responsible,
            priority=priority,
            progress=progress,
            start=start,
            deadline=deadline,
            tags=tags,
            reminder=reminder,
            key=key
        )

    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Task "{}" added. It\'s key - {}'.format(name, key))
    return 0


def _edit_task(args, library) -> int:
    key = args.pop(ParserArgs.KEY.name)

    try:
        name = args.pop(ParserArgs.NEW_NAME.dest)
        name = check_str_len(name)

        description = args.pop(ParserArgs.TASK_DESCRIPTION.dest)
        description = check_str_len(description)

        linked = args.pop(ParserArgs.TASK_LINKED.dest)
        linked = check_link_correctness(linked, action=ParserArgs.SET)

        responsible = args.pop(ParserArgs.TASK_RESPONSIBLE.dest)
        responsible = check_responsible_correctness(responsible,
                                                    action=ParserArgs.SET)

        priority = args.pop(ParserArgs.TASK_PRIORITY.dest)
        priority = check_priority_correctness(priority, action=ParserArgs.SET)

        progress = args.pop(ParserArgs.TASK_PROGRESS.dest)
        progress = check_progress_correctness(progress, action=ParserArgs.SET)

        start = args.pop(ParserArgs.TASK_START.dest)
        start = check_time_format(start, action=ParserArgs.SET)

        deadline = args.pop(ParserArgs.TASK_DEADLINE.dest)
        deadline = check_time_format(deadline, action=ParserArgs.SET)

        tags = args.pop(ParserArgs.TASK_TAGS.dest)
        tags = check_tags_correctness(tags, action=ParserArgs.SET)

        reminder = args.pop(ParserArgs.TASK_REMINDER.dest)
        reminder = check_reminder_format(reminder, action=ParserArgs.SET)

        status = args.pop(ParserArgs.TASK_STATUS.dest)
        status = check_status_correctness(status, action=ParserArgs.SET)

    except ValueError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    try:
        library.edit_task(
            key=key,
            name=name,
            description=description,
            status=status,
            parent=args.pop(ParserArgs.TASK_PARENT.dest),
            linked=linked,
            responsible=responsible,
            priority=priority,
            progress=progress,
            start=start,
            deadline=deadline,
            tags=tags,
            reminder=reminder,
        )

    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Task with key "{}" edited'.format(key))
    return 0


def _del_task(args, library) -> int:
    try:
        tasks = library.remove_task(
            key=args.pop(ParserArgs.KEY.name),
            recursive=args.pop(ParserArgs.RECURSIVE.dest)
        )

    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    for task in tasks:
        print('Task "{}" deleted'.format(task.name))
    return 0


def _show_task(key, library, long) -> int:
    try:
        task = library.find_task(key)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Main task:')
    if long:
        Printer.print_task_fully(task)
    else:
        Printer.print_task_briefly(task)

    sub_tasks = library.task_controller.get_sub_tasks(task)
    if sub_tasks:
        Printer.print_tasks(sub_tasks, "Sub tasks:")
    return 0


def _find_task(name, library) -> int:
    try:
        tasks = library.find_task(name=name)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Search:')
    Printer.print_tasks(tasks, 'Result for "{}"'.format(name))
    return 0


def _activate_task(key, library) -> int:
    try:
        task = library.activate_task(key)
    except AppError as e:
        sys.stderr.write(str(e))
        return ERROR_CODE

    print('Participation in task "{}" is confirmed!'.format(task.name))
    return 0
