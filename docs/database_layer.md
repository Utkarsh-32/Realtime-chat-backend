*1. What the database engine does ?*
Ans: The database engine manages the pool of connections between the app and the database and it converts the async sqlalchemy msgs into database protocol messages. It doesnt run the queries itself - sessions do - it just manages the infrastructure they use.

*2. What an async session is ?*
Ans: The session tracks changes to objects, manages transactions and run sql queries. Async just means that it does not block the event loop while waiting.

*3. What Dependency injection is?*
Ans: Dependency injection means that my framework automatically calls the functions I list as dependencies and resolves their return values and passes them to the endpoint. It centralizes shared resources and prevents manual setup/teardown.

*4. Why we need a Base class?*
Ans: We need a Base class because this is a common and global template which all my models will follow and it is the ORM object which will convert my python object to sql instructions. Base also stores metadata so alembic knows what tables exist.

*5. What migrations are and why do we use Alembic?*
Ans: Migrations are the changes that we make to the database for example adding a column or a new table or some constraints to the existing columns etc. Migrations are what take these changes and actually apply them to the database. Alembic is what is used for doing migrations in a fastapi app. Alembic allows us to apply migrations to the database.