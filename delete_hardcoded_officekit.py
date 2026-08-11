from connection.db_officekit import get_db
import logging

logger = logging.getLogger("officekit_delete_hardcoded")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
logger.addHandler(ch)

def run():
    company_code = "A100"
    sql_conn = get_db(company_code)
    
    if not sql_conn:
        logger.error("No SQL connection.")
        return
        
    cursor = sql_conn.cursor()
    
    duplicate_codes = [
        "EMP-9278", "EMP-2592", "EMP-3025", "EMP-7169", "EMP-4575",
        "EMP-8379", "EMP-7943", "EMP-1934", "EMP-6789", "EMP-5980",
        "EMP-8173", "EMP-4955", "EMP-5087", "EMP-7721", "EMP-3848",
        "EMP-2981", "EMP-3918", "EMP-4804", "EMP-5911", "EMP-2783",
        "EMP-1222"
    ]
    
    for code in duplicate_codes:
        logger.info(f"Marking {code} as IsDelete=1 in OfficeKit HR_EMP_MASTER")
        try:
            cursor.execute("""
                UPDATE HR_EMP_MASTER 
                SET IsDelete = 1 
                WHERE Emp_Code = %s
            """, (code,))
            sql_conn.commit()
        except Exception as e:
            logger.error(f"Failed to delete {code} in OfficeKit: {e}")
            sql_conn.rollback()

    logger.info("Finished deleting duplicates from OfficeKit.")

if __name__ == "__main__":
    run()
