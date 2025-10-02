def get_contacts():
    return ['john', 'jake']

def get_users():
    return {'online': ['john', 'jake', '10.10.123.102'], 'offline': ['10.10.123.102', '10.10.123.104']}

def get_user_list():
    users = get_users()
    users_list = users['online'] + users['offline']
    return users_list