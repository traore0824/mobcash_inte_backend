from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):

    def create_user(self, email,phone, password=None):
        if not email:
            raise ValueError("EMAIL_MISSED")
        email = self.normalize_email(email)

        user = self.model(email=email, phone=phone)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email,
        phone,
        password=None,
    ):
        user = self.create_user(
            email=email,
            phone=phone,
        )
        user.is_active = True
        user.is_supperuser = True
        user.set_password(password)
        user.is_staff = True
        user.save(using=self._db)
        return user
