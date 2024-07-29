import database
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

with database.DbClient() as db:

    # 全ての権利が対象
    for prop in db.Properties.find({
        'Ignored': {'$exists': False},
    }):
        
        if not 'NextProcedureLimit' in prop:
            continue

        logger.info('%s / %s / %s', prop['_id'], prop['Law'], prop['RegistrationNumber'])
        x = prop['NextProcedureLimit']

        # 次回期限の更新
        db.renew_limit_date(prop['_id'])

        updated = db.Properties.find_one({'_id': prop['_id']}, {'NextProcedureLimit':1})

        if not 'NextProcedureLimit' in updated:
            logger.warning('NextProcedureLimit is deleted.')
        elif x != updated['NextProcedureLimit']:
            logger.warning('NextProcedureLimit is changed %s -> %s', x, updated['NextProcedureLimit'])
